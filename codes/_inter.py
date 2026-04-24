import os
import sys
from recorder import State
from codes.base_gameLogic import Action, GameOutcome
from codes.base_rule import RuleManager

class InteractiveGame:
    """交互式BABA IS YOU游戏"""
    
    def __init__(self, map_text=None):
        """初始化游戏"""
        self.map_text = map_text or self.get_default_map()
        self.grid = State.from_text(self.map_text)
        self.game_state = GameOutcome.Continue
        self.game_over = False
        self.step_count = 0
        
    def get_default_map(self):
        """获取默认地图"""
        return '''
        .........
        .B02.....
        .S03.....
        ......b..
        ..s......'''
    
    def clear_screen(self):
        """清屏"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def display_game(self):
        """显示游戏界面"""
        self.clear_screen()
        print("=" * 50)
        print("🎮 BABA IS YOU - 交互式游戏")
        print("=" * 50)
        print()
        
        # 显示地图
        print("📋 当前地图:")
        print(self.grid)
        print()
        
        # 显示游戏状态
        print("📊 游戏状态:")
        print(f"   步数: {self.step_count}")
        print(f"   状态: {self.game_state}")
        print()
        
        # 显示规则
        print("📜 当前规则:")
        self.display_rules()
        print()
        
    
    def get_game_status(self):
        """获取游戏状态"""
        you_entities = self.grid.get_entities_by_prop('YOU')
        if len(you_entities) == 0:
            return "💀 失败 - 没有YOU实体"
        
        win_entities = self.grid.get_entities_by_prop('WIN')
        if len(win_entities) == 0:
            return "🎯 进行中 - 寻找WIN实体"
        
        return "🎉 胜利 - 找到WIN实体"
    
    def display_rules(self):
        """显示当前规则"""
        rules = self.grid.rule_manager.detect_all_rules()
        if rules:
            for rule in rules:
                print(f"   • {rule}")
        else:
            print("   • 暂无规则")
    
    def display_controls(self):
        """显示控制说明"""
        print("🎮 控制说明:")
        print("   移动: w(上) s(下) a(左) d(右)")
        print("   特殊: 空格(等待) z(撤销) r(重启) q(退出)")
        print("   输入: ", end="")
    
    def get_user_input(self):
        """获取用户输入"""
        try:
            user_input = input().strip().lower()
            # 处理单个字符输入
            if len(user_input) == 1:
                return Action.from_char(user_input)
            return Action.wait
            
        except ValueError:
            print("❌ 无效输入，请重试")
            return Action.wait
        except KeyboardInterrupt:
            return Action.quit
    
    def handle_game_outcome(self):
        """处理游戏结果"""
        outcome = self.game_state
        if outcome == GameOutcome.Win:
            print("🎉 恭喜！你赢了！")
            self.game_over = True
        elif outcome == GameOutcome.Defeat:
            print("💀 游戏结束！你失败了！")
            self.game_over = True
        elif outcome == GameOutcome.Still:
            print("⏸️ 尝试r重启或z撤回")
        elif outcome == GameOutcome.Quit:
            print("👋 再见！")
            self.game_over = True
    
    def run(self):
        """运行游戏主循环"""
        print("🚀 游戏开始！")
        input("按回车键继续...")
        
        while not self.game_over:
            self.display_game()
            
            # 获取用户输入
            action = self.get_user_input()
            
            # 执行动作
            try:
                self.grid, self.game_state, _ = self.grid.step(action)
                self.step_count += 1
                
                # 处理游戏结果
                self.handle_game_outcome()
                
                # 如果游戏结束，显示最终结果
                if self.game_over:
                    self.display_final_result()
                    break
                    
            except Exception as e:
                print(f"❌ 执行动作时出错: {e}")
                input("按回车键继续...")
    
    def display_final_result(self):
        """显示最终结果"""
        self.clear_screen()
        print("=" * 50)
        print("🏁 游戏结束")
        print("=" * 50)
        print()
        
        print("📊 最终统计:")
        print(f"   总步数: {self.step_count}")
        print(f"   最终状态: {self.game_state}")
        print()
        
        print("📋 最终地图:")
        print(self.grid)
        print()
        
        print("📜 最终规则:")
        self.display_rules()
        print()
        
        input("按回车键退出...")

def create_custom_map():
    """创建自定义地图"""
    print("🗺️ 创建自定义地图")
    print("输入地图文本（用.表示空格，每行用换行分隔）:")
    print("示例:")
    print("B02.....")
    print("S03.....")
    print(".....b..")
    print(".s......")
    print()
    
    lines = []
    while True:
        line = input("输入一行（或输入'end'结束）: ").strip()
        if line.lower() == 'end':
            break
        if line:
            lines.append(line)
    
    if lines:
        return '\n'.join(lines)
    return None

def main():
    """主函数"""
    print("🎮 BABA IS YOU - 交互式游戏")
    print("=" * 40)
    print("1. 使用默认地图")
    print("2. 创建自定义地图")
    print("3. 退出")
    print("=" * 40)
    
    choice = input("请选择 (1-3): ").strip()
    
    if choice == '1':
        game = InteractiveGame()
        game.run()
    elif choice == '2':
        custom_map = create_custom_map()
        if custom_map:
            game = InteractiveGame(custom_map)
            game.run()
        else:
            print("❌ 未创建地图，退出游戏")
    elif choice == '3':
        print("👋 再见！")
    else:
        print("❌ 无效选择")

if __name__ == "__main__":
    main()