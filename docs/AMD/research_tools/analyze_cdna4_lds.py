"""Payload-only dense GEMM roofline and illustrative register budgets; not a benchmark."""
from pathlib import Path
import json,csv,math
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'sources/cdna4_lds_analysis';OUT.mkdir(parents=True,exist_ok=True)
FORMATS=[
 ('FP32',4,[(16,16,4,32),(32,32,2,64)]),
 ('FP64',8,[(16,16,4,64)]),
 ('FP16/BF16',2,[(16,16,32,16),(32,32,16,32)]),
 ('FP8 F8F6F4 path',1,[(16,16,128,32),(32,32,64,64)]),
 ('FP6 packed',.75,[(16,16,128,16),(32,32,64,32)]),
 ('FP4 packed',.5,[(16,16,128,16),(32,32,64,32)]),
 ('INT8',1,[(16,16,64,16),(32,32,32,32)]),
]
native=[];wave=[];registers=[]
for name,s,shapes in FORMATS:
 for m,n,k,t in shapes:
  p=4*2*m*n*k/t
  load=s*k*(m+n)
  native.append(dict(format=name,m=m,n=n,k=k,cycles_per_wave=t,peak_ops_per_cu_cycle=p,ab_bytes_per_wave=load,ab_bytes_per_cu_cycle=4*load/t))
 if name in ['FP16/BF16','FP8 F8F6F4 path','FP6 packed','FP4 packed']:
  m,n,ki,t=shapes[-1];p=4*2*m*n*ki/t
  for side in [32,64,128]:
   demand=p*s/side
   wave.append(dict(format=name,wave_m=side,wave_n=side,ab_read_bytes_per_cu_cycle=demand,lds_fraction=demand/256))
   rc=side*side/64
   rab=2*side*ki*s/256
   overhead=16;buffers=2
   arch=math.ceil((buffers*rab+overhead)/8)*8
   acc=rc
   total=math.ceil((arch+acc)/8)*8
   assert arch<=256 and acc<=256 and total<=512
   registers.append(dict(format=name,wave_tile=f'{side}x{side}',native_k=ki,accumulator_regs_per_lane=rc,ab_regs_per_lane_one_buffer=rab,ab_buffers=buffers,assumed_other_arch_regs_per_lane=overhead,allocated_regs_per_lane=total,rf_only_max_waves_per_simd=min(8,512//total),allocated_kB_per_wave=total/4,ab_read_bytes_per_cu_cycle=demand))
scale=[]
for name,s,p in [('MXFP8',1,8192),('MXFP6',.75,16384),('MXFP4',.5,16384)]:
 scale.append(dict(format=name,scale_bytes_per_element=1/32,square_wave_side_lower_bound=p*(s+1/32)/256,read_B_per_cu_cycle_32=p*(s+1/32)/32,read_B_per_cu_cycle_64=p*(s+1/32)/64))
staging=[]
for side in [32,64,128]:
 # Four waves in 2x2 layout, FP16, k_LDS_buffer=64, two LDS buffers.
 p=4096;s=2;wm=wn=side;bm=bn=2*side;bk=64
 cycles=2*bm*bn*bk/p
 unique=s*bk*(bm+bn)
 read=4*s*bk*(wm+wn)
 staging.append(dict(wave_tile=f'{side}x{side}',workgroup_tile=f'{bm}x{bn}',lds_buffer_k=bk,lds_double_buffer_kB=2*unique/1024,read_B_per_cu_cycle=read/cycles,stage_write_B_per_cu_cycle=unique/cycles))
data={'date':'2026-11-03','assumptions':['4 matrix engines per CU; native table cycles are per-wave instruction cycles','Dense, FP32 accumulation except FP64; retained C/D with in-place accumulation; no inner-loop C/D LDS traffic','Ideal packed A/B payload; no bank conflicts, lane duplication, spills, or scaling metadata in native/wave/register tables','No cross-wave LDS multicast assumed; each wave loads its own operand fragments','Register table uses 32x32 native MFMA, full A/B two-buffer register staging, 16 illustrative ordinary registers/lane overhead; C in AGPR','RF max waves excludes LDS/SGPR/scheduler/barrier limitations; actual liveness and allocation may differ','1 kB=1024 B; LDS read peak 256 byte/CU/cycle is not a promise of extra simultaneous write throughput'],
 'native':native,'wave_tiles':wave,'registers':registers,'scales':scale,'staging':staging}
(OUT/'analysis.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
for key in ['native','wave_tiles','registers','scales','staging']:
 with (OUT/(key+'.csv')).open('w',newline='',encoding='utf-8-sig') as f:
  writer=csv.DictWriter(f,fieldnames=list(data[key][0]));writer.writeheader();writer.writerows(data[key])
for key in ['native','registers','scales','staging']:print(key,json.dumps(data[key]))
