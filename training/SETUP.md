# Training environment setup

Local only. Nothing here touches AWS.

## Verified environment

| Item | Value |
|---|---|
| OS | Windows 11 + WSL2, Ubuntu 24.04 |
| GPU | RTX 4060 Laptop, 8 GB (about 7 GB usable; Windows uses roughly 1 GB) |
| Driver | NVIDIA 591.91 (CUDA 13.1). Only the Windows driver is needed; do not install a Linux driver in WSL |
| Python | 3.12 (venv created with `uv`) |
| Torch | 2.14.1, CUDA 13.0 build |

## One-time setup

```bash
# inside WSL2 Ubuntu
curl -LsSf https://astral.sh/uv/install.sh | sh      # user-space, no sudo
uv venv ~/venvs/playground --python 3.12
uv pip install --python ~/venvs/playground/bin/python -r training/requirements.txt \
  --index-url https://download.pytorch.org/whl/cu130 \
  --extra-index-url https://pypi.org/simple --index-strategy unsafe-best-match
```

`uv` is used because Ubuntu's `python3-venv` package needs sudo. With sudo available, plain
`python3 -m venv` plus `pip` works the same.

## Where things live

- The repo stays on the Windows filesystem. Source files are small, so reading them over
  `/mnt/c` is fine. Run `git` from the Windows side.
- The venv (`~/venvs/playground`), the Hugging Face cache (`HF_HOME=~/work/hf`) and training
  outputs live on the Linux filesystem, because model and dataset I/O over `/mnt/c` is slow.

## Gotchas hit during setup

- **Silent install failure.** `--index-url` pointing at the PyTorch index alone cannot resolve
  torch's non-CUDA dependencies; add PyPI as an extra index. Do not hide installer output with
  `| tail`, it masked this error once.
- **Git Bash path mangling.** Git Bash rewrites `/mnt/...` paths when invoking `wsl`. Call WSL
  from PowerShell, or use `MSYS_NO_PATHCONV=1`.
- **PowerShell variable expansion.** `$HOME` inside double-quoted strings is expanded by
  PowerShell to the Windows path before WSL sees it. Use literal `/home/<user>` paths.
- **VRAM headroom.** Close browsers and other GPU apps before training.

## Audit

`python -m pip_audit` reported no known vulnerabilities at the pinned versions on 2026-10-25.
Re-run it whenever the pins change.
