import pygame
import random
import sys

pygame.init()

WIDTH, HEIGHT = 900, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Pong - Player vs AI")
clock = pygame.time.Clock()

# Colors
WHITE = (240, 240, 240)
GRAY = (100, 100, 100)
BLACK = (15, 15, 20)

# Paddle / ball settings
PADDLE_W, PADDLE_H = 12, 100
BALL_SIZE = 14
PLAYER_SPEED = 7
AI_MAX_SPEED = 6
WIN_SCORE = 7

font_big = pygame.font.Font(None, 90)
font_small = pygame.font.Font(None, 36)


class Paddle:
    def __init__(self, x):
        self.rect = pygame.Rect(x, HEIGHT // 2 - PADDLE_H // 2, PADDLE_W, PADDLE_H)

    def move(self, dy):
        self.rect.y += dy
        self.rect.clamp_ip(screen.get_rect())


class Ball:
    def __init__(self):
        self.rect = pygame.Rect(0, 0, BALL_SIZE, BALL_SIZE)
        self.reset(direction=random.choice((-1, 1)))

    def reset(self, direction):
        self.rect.center = (WIDTH // 2, HEIGHT // 2)
        self.vx = 5 * direction
        self.vy = random.uniform(-4, 4)
        self.speed_multiplier = 1.0

    def update(self):
        self.rect.x += self.vx * self.speed_multiplier
        self.rect.y += self.vy * self.speed_multiplier

        # Bounce off top/bottom
        if self.rect.top <= 0:
            self.rect.top = 0
            self.vy = abs(self.vy)
        elif self.rect.bottom >= HEIGHT:
            self.rect.bottom = HEIGHT
            self.vy = -abs(self.vy)


def ai_move(paddle, ball):
    """Simple AI: track the ball when it's coming toward us, drift to center otherwise."""
    if ball.vx > 0:
        # Predict slightly ahead of ball position, with a bit of imperfection
        target = ball.rect.centery + ball.vy * 5
    else:
        target = HEIGHT // 2

    diff = target - paddle.rect.centery
    # Dead zone so the AI doesn't jitter
    if abs(diff) > 10:
        paddle.move(max(-AI_MAX_SPEED, min(AI_MAX_SPEED, diff)))


def paddle_bounce(ball, paddle, direction):
    """Bounce ball off paddle, angle based on where it hit."""
    offset = (ball.rect.centery - paddle.rect.centery) / (PADDLE_H / 2)
    ball.vx = abs(ball.vx) * direction
    ball.vy = offset * 6
    ball.speed_multiplier = min(ball.speed_multiplier + 0.05, 2.0)


def draw(player, ai, ball, player_score, ai_score, message=None):
    screen.fill(BLACK)

    # Center dashed line
    for y in range(0, HEIGHT, 30):
        pygame.draw.rect(screen, GRAY, (WIDTH // 2 - 2, y, 4, 15))

    pygame.draw.rect(screen, WHITE, player.rect)
    pygame.draw.rect(screen, WHITE, ai.rect)
    pygame.draw.ellipse(screen, WHITE, ball.rect)

    # Scores
    p_text = font_big.render(str(player_score), True, GRAY)
    a_text = font_big.render(str(ai_score), True, GRAY)
    screen.blit(p_text, (WIDTH // 4 - p_text.get_width() // 2, 30))
    screen.blit(a_text, (3 * WIDTH // 4 - a_text.get_width() // 2, 30))

    if message:
        msg = font_small.render(message, True, WHITE)
        screen.blit(msg, (WIDTH // 2 - msg.get_width() // 2, HEIGHT // 2 + 60))

    pygame.display.flip()


def main():
    player = Paddle(30)
    ai = Paddle(WIDTH - 30 - PADDLE_W)
    ball = Ball()
    player_score = 0
    ai_score = 0
    paused = True
    game_over = False

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
                if event.key == pygame.K_SPACE:
                    if game_over:
                        player_score = ai_score = 0
                        game_over = False
                        ball.reset(direction=random.choice((-1, 1)))
                    paused = False

        keys = pygame.key.get_pressed()
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            player.move(-PLAYER_SPEED)
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            player.move(PLAYER_SPEED)

        if not paused and not game_over:
            ai_move(ai, ball)
            ball.update()

            # Paddle collisions
            if ball.rect.colliderect(player.rect) and ball.vx < 0:
                ball.rect.left = player.rect.right
                paddle_bounce(ball, player, direction=1)
            elif ball.rect.colliderect(ai.rect) and ball.vx > 0:
                ball.rect.right = ai.rect.left
                paddle_bounce(ball, ai, direction=-1)

            # Scoring
            if ball.rect.right < 0:
                ai_score += 1
                ball.reset(direction=-1)
                paused = True
            elif ball.rect.left > WIDTH:
                player_score += 1
                ball.reset(direction=1)
                paused = True

            if player_score >= WIN_SCORE or ai_score >= WIN_SCORE:
                game_over = True

        if game_over:
            winner = "You win!" if player_score > ai_score else "AI wins!"
            message = f"{winner}  Press SPACE to play again"
        elif paused:
            message = "Press SPACE to serve  |  W/S or Up/Down to move"
        else:
            message = None

        draw(player, ai, ball, player_score, ai_score, message)
        clock.tick(60)


if __name__ == "__main__":
    main()
