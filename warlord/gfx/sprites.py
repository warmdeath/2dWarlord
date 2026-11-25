"""Pre-rendered soldier sprites for formation ranks (hundreds of soldiers at full frame rate)."""
import math

import pygame

from .rig import compute_pose, draw_humanoid

_cache = {}
W, H = 72, 72
FX, FY = 36, 60


def soldier_sprite(proto, state, frame, facing, shade=1.0, action=None):
    """proto: a Humanoid used as a template (look + equipment)."""
    key = (id(proto), state, frame, facing, round(shade, 2), action)
    s = _cache.get(key)
    if s is not None:
        return s
    old = (proto.state, proto.walk_phase, proto.facing, proto.action, proto.anim_t, proto.blocking)
    proto.state = state
    proto.walk_phase = frame / 8.0 * math.tau
    proto.anim_t = frame * 0.1
    proto.facing = facing
    proto.blocking = action == "block"
    if action == "block":
        proto.action = {"kind": "block"}
    elif action == "attack":
        mv = proto.weapon_def.moves.get("combo", [None])[0] if proto.weapon_def.moves else None
        proto.action = {"kind": "attack", "move": mv, "t": mv.windup + mv.active * 0.5} if mv else None
    elif action == "bow":
        proto.action = {"kind": "bow", "draw": 0.8, "aim": -0.6}
    else:
        proto.action = None
    proto.pose = compute_pose(proto)
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    draw_humanoid(s, proto, FX, FY)
    if shade != 1.0:
        v = int(255 * shade)
        s.fill((v, v, v, 255), special_flags=pygame.BLEND_RGBA_MULT)
    proto.state, proto.walk_phase, proto.facing, proto.action, proto.anim_t, proto.blocking = old
    _cache[key] = s
    if len(_cache) > 6000:
        _cache.clear()
    return s
