"""Logical matrix operand traffic, distinct from physical RF port bandwidth."""
from pathlib import Path
import csv
import json

ROOT = Path(__file__).resolve().parents[1]


def analyze(g):
    data = json.loads((ROOT / f'sources/cdna{g}_lds_analysis/analysis.json').read_text(encoding='utf-8'))
    rows = []
    for r in data['native']:
        if g == 4:
            if r['m'] != 32 or r['format'] not in ['FP16/BF16', 'FP8 F8F6F4 path', 'FP6 packed', 'FP4 packed', 'INT8']:
                continue
            name, m, n, k, p = r['format'], r['m'], r['n'], r['k'], r['peak_ops_per_cu_cycle']
            ab = r['ab_bytes_per_cu_cycle']
        else:
            if r['format'] == 'FP32': continue
            name, m, n, k, p = r['format'], r['native_m'], r['native_n'], r['native_k'], r['peak_ops_per_wgp_cycle']
            ab = r['ab_required_B_per_wgp_cycle']
        cd = p * 4 / (2 * k)
        rows.append(dict(format=name, m=m, n=n, k=k, target_ops_per_unit_cycle=p,
                         ab_logical_read_B_per_unit_cycle=ab,
                         c_logical_read_B_per_unit_cycle=cd,
                         d_logical_write_B_per_unit_cycle=cd,
                         matrix_total_logical_read_B_per_unit_cycle=ab+cd))
    w, wg, kr, s, p = (64, 128, 16, 2, 4096) if g == 4 else (128, 256, 128, 1, 32768)
    native_m, native_n = (32, 32) if g == 4 else (16, 16)
    count = w*w//(native_m*native_n)
    ab_per_inst = kr*(native_m+native_n)*s
    unique = kr*(w+w)*s
    c_bytes = w*w*4
    total_ops = 2*w*w*kr
    cycles = 4*total_ops/p  # Four independent waves in the CU/WGP at target aggregate peak.
    example = dict(format='FP16/BF16' if g == 4 else 'FP8', wave_tile=f'{w}x{w}',
                   workgroup_tile=f'{wg}x{wg}', live_k=kr, native_instructions_per_wave=count,
                   wave_ab_unique_bytes=unique, wave_ab_logical_consumed_bytes=count*ab_per_inst,
                   wave_c_logical_read_bytes=c_bytes, wave_d_logical_write_bytes=c_bytes,
                   four_wave_target_cycles=cycles,
                   lds_to_vgpr_payload_write_B_per_unit_cycle=4*unique/cycles,
                   ab_logical_read_B_per_unit_cycle=4*count*ab_per_inst/cycles,
                   c_logical_read_B_per_unit_cycle=4*c_bytes/cycles,
                   d_logical_write_B_per_unit_cycle=4*c_bytes/cycles)
    example['total_logical_read_B_per_unit_cycle'] = example['ab_logical_read_B_per_unit_cycle']+example['c_logical_read_B_per_unit_cycle']
    example['total_logical_write_B_per_unit_cycle'] = example['lds_to_vgpr_payload_write_B_per_unit_cycle']+example['d_logical_write_B_per_unit_cycle']
    result = dict(scope=f'CDNA{g}, per '+('CU' if g == 4 else 'WGP')+' per cycle',
                  physical_rf_peak_read_B_per_unit_cycle=None,
                  physical_rf_peak_write_B_per_unit_cycle=None,
                  assumptions=['Dense target-peak normalization, not measured instruction latency or RF bandwidth',
                               'A/B values counted at each matrix instruction, before operand reuse/source-cache hits',
                               'C read and D write each count 4*m*n bytes per instruction; FP32/int32 accumulation',
                               'No physical RF array reads/writes inferred: forwarding, caching, packing, replication and ports are not modeled',
                               'LDS input writes count packed A/B payload only; scale registers, padding, VALU, addresses and epilogue excluded',
                               'CDNA4 C/D may be in AGPR or VGPR; shared capacity does not prove shared port topology',
                               '4 SIMD allocation assumed balanced when dividing aggregate rates by 4'],
                  native_operand_traffic=rows, example=example)
    if g == 5:
        result['fp8_128x128_reuse_scenarios'] = [
            dict(scenario='No source-cache savings', a_read=1024, b_read=1024, total=2048),
            dict(scenario='Hypothetical A-only cache hit reuse x8', a_read=128, b_read=1024, total=1152),
            dict(scenario='Both A/B ideal reuse x8; traffic floor only, not a hardware guarantee', a_read=128, b_read=128, total=256)]
    return result


def main():
    for g in [4, 5]:
        data = analyze(g)
        folder = ROOT / f'sources/cdna{g}_lds_analysis'
        (folder/'vgpr_bandwidth.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
        rows = data['native_operand_traffic']
        with (folder/'vgpr_bandwidth.csv').open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        print(json.dumps({'generation':g, 'rows':len(rows), 'example':data['example']}))


if __name__ == '__main__': main()
