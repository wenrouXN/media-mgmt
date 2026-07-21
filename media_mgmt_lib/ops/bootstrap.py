"""Import all op modules to register handlers."""
from __future__ import annotations

import media_mgmt_lib.ops.moviepilot  # noqa: F401
import media_mgmt_lib.ops.hdhive  # noqa: F401  # alias → nextfind
import media_mgmt_lib.ops.telegram_music  # noqa: F401
import media_mgmt_lib.ops.douyin  # noqa: F401
import media_mgmt_lib.ops.bilibili  # noqa: F401
import media_mgmt_lib.ops.tiktok  # noqa: F401
import media_mgmt_lib.ops.hybrid  # noqa: F401
import media_mgmt_lib.ops.playlist  # noqa: F401
import media_mgmt_lib.ops.hongguo  # noqa: F401
import media_mgmt_lib.ops.nextfind  # noqa: F401

# clouddrive may fail import when protobuf runtime < gencode; keep optional
try:
    import media_mgmt_lib.ops.clouddrive  # noqa: F401
except Exception:  # noqa: BLE001
    pass
