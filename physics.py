import math
import random

import pygame


WIDTH, HEIGHT = 960, 640
GRAVITY = 900
FRICTION = 0.995
BOUNCE = 0.8


class Ball:
    def __init__(self, x, y, radius, color, mass=1.0):
        self.x = float(x)
        self.y = float(y)
        self.radius = radius
        self.color = color
        self.mass = mass
        self.vx = random.uniform(-180, 180)
        self.vy = random.uniform(-40, 40)

    def update(self, dt):
        self.vy += GRAVITY * dt
        self.x += self.vx * dt
        self.y += self.vy * dt

        if self.x - self.radius < 0:
            self.x = self.radius
            self.vx = abs(self.vx) * BOUNCE
        elif self.x + self.radius > WIDTH:
            self.x = WIDTH - self.radius
            self.vx = -abs(self.vx) * BOUNCE

        if self.y - self.radius < 0:
            self.y = self.radius
            self.vy = abs(self.vy) * BOUNCE
        elif self.y + self.radius > HEIGHT:
            self.y = HEIGHT - self.radius
            self.vy = -abs(self.vy) * BOUNCE
            self.vx *= FRICTION

        if abs(self.vx) < 1:
            self.vx = 0
        if abs(self.vy) < 1:
            self.vy = 0

    def draw(self, screen):
        pygame.draw.circle(screen, self.color, (int(self.x), int(self.y)), self.radius)


def resolve_ball_collision(a, b):
    dx = b.x - a.x
    dy = b.y - a.y
    distance_sq = dx * dx + dy * dy
    min_distance = a.radius + b.radius

    if distance_sq == 0:
        dx, dy = 1, 0
        distance_sq = 1

    if distance_sq < min_distance * min_distance:
        distance = math.sqrt(distance_sq)
        nx = dx / distance
        ny = dy / distance
        overlap = min_distance - distance

        total_mass = a.mass + b.mass
        if total_mass == 0:
            return

        push_a = overlap * (b.mass / total_mass)
        push_b = overlap * (a.mass / total_mass)

        a.x -= nx * push_a
        a.y -= ny * push_a
        b.x += nx * push_b
        b.y += ny * push_b

        rvx = b.vx - a.vx
        rvy = b.vy - a.vy
        velocity_along_normal = rvx * nx + rvy * ny

        if velocity_along_normal < 0:
            restitution = 0.85
            impulse = -(1 + restitution) * velocity_along_normal / (1 / a.mass + 1 / b.mass)
            impulse_x = impulse * nx
            impulse_y = impulse * ny

            a.vx -= impulse_x / a.mass
            a.vy -= impulse_y / a.mass
            b.vx += impulse_x / b.mass
            b.vy += impulse_y / b.mass


def resolve_circle_rect_collision(circle, rect, push_strength=1.0):
    prev_x = circle.get("prev_x", circle["x"])
    prev_y = circle.get("prev_y", circle["y"])

    cx = circle["x"]
    cy = circle["y"]
    r = circle["radius"]
    rx = rect["x"]
    ry = rect["y"]
    rw = rect["width"]
    rh = rect["height"]

    closest_x = max(rx, min(cx, rx + rw))
    closest_y = max(ry, min(cy, ry + rh))

    dx = cx - closest_x
    dy = cy - closest_y
    distance_sq = dx * dx + dy * dy

    if distance_sq >= r * r:
        return False

    if distance_sq == 0:
        rect_center_x = rx + rw / 2
        rect_center_y = ry + rh / 2
        dx = cx - rect_center_x
        dy = cy - rect_center_y
        dist = math.hypot(dx, dy) or 1.0
        nx = dx / dist
        ny = dy / dist
        overlap = r + 0.5
    else:
        dist = math.sqrt(distance_sq)
        nx = dx / dist
        ny = dy / dist
        overlap = r - dist + 0.5

    movement_x = cx - prev_x
    movement_y = cy - prev_y
    movement_len = math.hypot(movement_x, movement_y)
    if movement_len > 0:
        move_nx = movement_x / movement_len
        move_ny = movement_y / movement_len
        if nx * move_nx + ny * move_ny < 0:
            nx *= -1
            ny *= -1

    circle["x"] += nx * overlap * push_strength
    circle["y"] += ny * overlap * push_strength
    return True


def create_demo_balls():
    balls = []
    for i in range(8):
        radius = random.randint(12, 22)
        x = random.randint(radius, WIDTH - radius)
        y = random.randint(radius, HEIGHT // 3)
        color = (
            random.randint(80, 255),
            random.randint(80, 255),
            random.randint(80, 255),
        )
        balls.append(Ball(x, y, radius, color, mass=max(1.0, radius / 10)))
    return balls


def run():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Simple Collision Physics")
    clock = pygame.time.Clock()
    balls = create_demo_balls()

    running = True
    while running:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        for i, ball in enumerate(balls):
            ball.update(dt)
            for other in balls[i + 1 :]:
                resolve_ball_collision(ball, other)

        screen.fill((18, 18, 28))

        for ball in balls:
            ball.draw(screen)

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    run()
