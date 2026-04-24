"""目标交互模拟器 - 负责模拟 TargetInteraction 产生的 ActionPlan

从 TargetInteraction 类中分离出模拟逻辑。
"""

from typing import TYPE_CHECKING, Dict, List, Tuple
from base_gameLogic import GameOutcome

if TYPE_CHECKING:
    from recorder import State, TargetInteraction
    from base_gameLogic import Action, Coord


class TargetSimulator:
    """负责模拟目标交互过程并生成 ActionPlan"""
    
    def __init__(self, data_manager, simulation_limit: int = 10):
        """初始化模拟器s
        
        Args:
            data_manager: DataManager 实例
        """
        self.data_manager = data_manager
        self.simulation_limit = simulation_limit
    
    def simulate_target(self, target: 'TargetInteraction', limit: int = 10) -> Dict[int, str]:
        """模拟目标交互，返回每个 ActionPlan 的后状态
        
        Args:
            target: 要模拟的目标交互
            limit: 最大模拟步数
        
        Returns:
            {plan_idx: gamestate_key} 字典，表示每个 ActionPlan 产生的 GameState
        """
        from recorder import State
        
        # 创建模拟用的 grid 副本
        sim_grid = State.quick_load(target.gridmap.quick_save())
        
        # 找到 YOU 实体并移动到起始位置
        you_entities = sim_grid.get_entities_by_prop('YOU')
        you_entity = you_entities[0] if you_entities else None

        sim_grid.move_entity(you_entity, target.start)
        
        # 确定模拟步数限制
        limit = self.simulation_limit or limit
        actual_limit = limit if (target.dir and 
                                (target.dir.has_prop('PUSH') or 
                                 target.dir.has_prop('TEXT'))) else 1
        # 模拟循环
        state_record = {}
        pre_state = target.gridmap._get_state_hash(updating=False)
        action_sequence = ''
        
        for step in range(1, actual_limit + 1):

            sim_grid, outcome, _ = sim_grid.step(target.action)
            post_state = sim_grid._get_state_hash(updating=True)
            action_sequence += str(target.action)

            # 如果状态不变，停止模拟
            if pre_state == post_state:
                break
            
            state_record[step] = (post_state, action_sequence)
            
            # 如果游戏结束，停止模拟
            if outcome != GameOutcome.Continue:
                break
            
            pre_state = post_state
        return state_record
    
    def extract_plans(self, target: 'TargetInteraction',
                     post_states: Dict[int, str]) -> List[Dict]:
        """从目标交互中提取 ActionPlan
        
        Args:
            target: 目标交互对象
            post_states: 模拟产生的后状态字典
        
        Returns:
            ActionPlan 列表，每个计划包含 {plan_key, pre_state, post_state, plan_idx, ...}
        """
        plans = []
        init_state = target.gridmap._get_state_hash(updating=False)
        pre_state = init_state
        
        for plan_idx, (post_state, action_sequence) in sorted(post_states.items()):
            plan_key = self._generate_plan_key(
                target.get_chain_index(), plan_idx, action_sequence
            )
            
            plan_data = {
                'plan_key': plan_key,
                'parent': {
                    'target_key': target.get_chain_index(),
                    'plan_idx': plan_idx,
                    'init_gamestate': init_state,
                    'pre_gamestate': pre_state,
                    'post_gamestate': post_state,
                    'action_name': target.action.name,
                    'start_coord': (int(target.start.x), int(target.start.y)),
                    'collision_coord': (int(target.collision.x), int(target.collision.y)) 
                                      if target.collision else None,
                    'dist': target.dist
                },
                'raw': {},   # 将由 evaluator 填充
                'norm': {}   # 将由 evaluator 填充
            }
            
            plans.append(plan_data)
            pre_state = post_state  # 下一个计划的前状态
        
        return plans
    
    @staticmethod
    def _generate_plan_key(target_key: str, plan_idx: int, action_sequence: str) -> str:
        """生成 ActionPlan 的唯一键"""
        return f"{target_key}_P{plan_idx}_{action_sequence}"
    
    def simulate_and_store(self, target: 'TargetInteraction') -> Dict:
        """模拟目标交互并存储所有数据（target + plans）
        
        Args:
            target: 要模拟的目标交互
        
        Returns:
            目标交互摘要字典
        """
        # 1. 模拟产生后状态
        post_states = self.simulate_target(target, limit=10)
        
        # 2. 提取 ActionPlan
        plans = self.extract_plans(target, post_states)
        
        # 3. 存储 ActionPlan 到 plan_manager
        for plan_data in plans:
            self.data_manager.plan_manager.put(plan_data['plan_key'], plan_data)
        
        # 4. 生成并返回目标交互摘要
        target_summary = {
            'target_key': target.get_chain_index(),
            'trans': {
                'pre_gamestate': target.gridmap._get_state_hash(updating=False),
                'post_gamestates': post_states,
                'len_chain': len(target.chain),
                'dist': target.dist,
                'action': target.action.name,
                'collision': str(target.collision)
            },
            'tile': self._get_tile_info(target),
            'plans': [plan['plan_key'] for plan in plans]  # 引用所有 ActionPlan
        }
        
        return target_summary
    
    @staticmethod
    def _get_tile_info(target: 'TargetInteraction') -> Dict:
        """获取 tile 信息"""
        dir_info = {}
        ind_info = {}
        
        if target.dir:
            dir_info = {
                str(ent.global_id): (ent.entity_id, ent.get_prop_one_hot()) 
                for ent in target.dir.get_all_entities()
            }
        
        if target.ind:
            ind_info = {
                str(ent.global_id): (ent.entity_id, ent.get_prop_one_hot()) 
                for ent in target.ind.get_all_entities()
            }
        
        return {'direct': dir_info, 'indirect': ind_info}
