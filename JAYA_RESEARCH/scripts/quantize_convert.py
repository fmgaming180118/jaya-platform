#!/usr/bin/env python3
"""Quantize or convert PyTorch checkpoint into packed NumPy weights suitable for NanoModel packing.

This script is a scaffold — it will attempt to load a PyTorch checkpoint, convert tensors to NumPy,
and call the packer if available in `JAYA_CORE`.
"""
import argparse
import os
import numpy as np

def try_import_packer():
    try:
        from src.brain_v2.format.packer import pack_state_dict
        return pack_state_dict
    except Exception:
        return None

def load_checkpoint(path: str):
    try:
        import torch
    except Exception as exc:
        raise SystemExit('Please install torch to load checkpoints') from exc
    ckpt = torch.load(path, map_location='cpu')
    # common patterns: {'model': state_dict} or state_dict directly
    if 'model' in ckpt and isinstance(ckpt['model'], dict):
        sd = ckpt['model']
    elif 'state_dict' in ckpt:
        sd = ckpt['state_dict']
    else:
        sd = ckpt
    return sd

def state_dict_to_numpy(sd: dict) -> dict:
    out = {}
    for k, v in sd.items():
        try:
            arr = v.cpu().numpy()
        except Exception:
            try:
                arr = np.array(v)
            except Exception:
                continue
        out[k] = arr
    return out

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--ckpt', required=True, help='PyTorch checkpoint path')
    p.add_argument('--out', required=True, help='Packed output bytes file')
    p.add_argument('--bits', type=int, default=4, help='Target quantization bits (informational)')
    args = p.parse_args()

    sd = load_checkpoint(args.ckpt)
    numpy_sd = state_dict_to_numpy(sd)
    packer = try_import_packer()
    if packer is None:
        print('packer not available. Writing raw numpy .npz as fallback.')
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        np.savez_compressed(args.out, **{k.replace('/', '__'): v for k, v in numpy_sd.items()})
    else:
        packed = packer(numpy_sd)
        with open(args.out, 'wb') as f:
            f.write(packed)
        print(f'Wrote packed state to {args.out}')

if __name__ == '__main__':
    main()
