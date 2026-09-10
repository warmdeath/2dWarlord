"""Terrain and authored overworld layout."""

import math

import pygame

from .config import GROUND_BASE, HEIGHT, WIDTH


def ground_y(x):
    """Return the smooth terrain height at a world-space x coordinate."""
    return GROUND_BASE + math.sin(x * 0.0035) * 45 + math.sin(x * 0.011 + 1.7) * 20


class WorldLayout:
    """Authored anchors and background scenery for the overworld."""

    def __init__(self):
        self.anchors = {
            "camp": 170,
            "farm": 420,
            "gate": 700,
            "market": 1220,
            "tent": 170,
            "mountain": 2050,
            "frontier": 2320,
        }
        self.tree_positions = (250, 530, 910, 1010, 1460, 1580, 1780, 2180, 2410)

    def draw_background(self, surf, camera_x):
        mountain_points = [(0, HEIGHT)]
        for screen_x in range(0, WIDTH + 20, 20):
            world_x = camera_x * 0.35 + screen_x * 0.35
            height = 250 + math.sin(world_x * 0.006) * 65 + math.sin(world_x * 0.014) * 25
            mountain_points.append((screen_x, int(height)))
        mountain_points.append((WIDTH, HEIGHT))
        pygame.draw.polygon(surf, (39, 48, 66), mountain_points)

        near_ridge = [(0, HEIGHT)]
        for screen_x in range(0, WIDTH + 20, 20):
            world_x = camera_x * 0.6 + screen_x * 0.6
            height = 315 + math.sin(world_x * 0.0045 + 1.5) * 38
            near_ridge.append((screen_x, int(height)))
        near_ridge.append((WIDTH, HEIGHT))
        pygame.draw.polygon(surf, (31, 43, 50), near_ridge)

        for tree_x in self.tree_positions:
            screen_x = int(tree_x - camera_x * 0.82)
            if -40 <= screen_x <= WIDTH + 40:
                tree_ground = int(ground_y(tree_x) + 5)
                trunk_top = tree_ground - 60
                pygame.draw.line(surf, (62, 43, 29), (screen_x, tree_ground), (screen_x, trunk_top), 8)
                pygame.draw.circle(surf, (35, 78, 55), (screen_x - 13, trunk_top + 8), 22)
                pygame.draw.circle(surf, (42, 94, 61), (screen_x + 10, trunk_top + 3), 25)

        waterfall_x = int(self.anchors["mountain"] - camera_x * 0.82)
        if -30 <= waterfall_x <= WIDTH + 30:
            waterfall_top = 205
            waterfall_bottom = int(ground_y(self.anchors["mountain"]) + 2)
            pygame.draw.polygon(
                surf,
                (95, 160, 178),
                [(waterfall_x - 10, waterfall_top), (waterfall_x + 7, waterfall_top),
                 (waterfall_x + 15, waterfall_bottom), (waterfall_x - 18, waterfall_bottom)],
            )
            pygame.draw.line(
                surf,
                (180, 220, 220),
                (waterfall_x - 2, waterfall_top),
                (waterfall_x - 4, waterfall_bottom),
                3,
            )
