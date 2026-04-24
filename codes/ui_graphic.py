from base_gameLogic import GameEngine


class Graphic():

    def __init__(self):
        pass

    def clear_screen(self):
        print("\033[H\033[J", end="")

    def render_gridworld(self, grid: GameEngine):
        print(grid.get_description())
    
    def render_state_summary(self, grid: GameEngine):
        print(f"Last Action: {grid.game_history.get_last_action() if grid.game_history else 'N/A'}")
        print(f'Current State: {grid.state}')

    def collect_user_action(self, grid: GameEngine) -> str:
        action_char = input(f'{grid.get_possible_actions()}:').strip().lower()
        return action_char
    
    def invalid_action(self, action_char: str):
        print(f"Invalid action: {action_char}. Please try again.")
    
    def summary(self, grid: GameEngine):
        self.clear_screen()
        print("=== Game State Summary ===")
        for item in grid.game_history.history:
            print(item)
        print("==========================")