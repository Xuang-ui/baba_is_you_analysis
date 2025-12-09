"""目标交互摘要器 - 负责生成 TargetInteraction 的摘要和索引

将原本在 TargetInteraction 中的摘要生成逻辑分离出来。
"""

from typing import TYPE_CHECKING, Optional, Dict, Any

if TYPE_CHECKING:
    from recorder import Gridmap, TargetInteraction
    from base_gameLogic import Tile


class TargetSummarizer:
    """负责生成 TargetInteraction 的摘要"""
    
    def __init__(self, target_simulator):
        self.target_simulator = target_simulator
    
    def compute_chain_index(self, target: 'TargetInteraction') -> str:
        """计算目标交互的唯一索引
        格式: statehash_collisioncoord_actionname
        Returns: 唯一索引字符串
        """
        pre_state = target.gridmap._get_state_hash(updating=False)
        action_name = target.action.value
        coord = str(target.collision) if target.collision else "None"
        return f"{pre_state}_{coord}_{action_name}"
    
    def calculate_push_chain(self, target: 'TargetInteraction') -> list:
        """计算推动链 
        从碰撞位置开始，沿着动作方向寻找所有可推动的 tile。
        Returns: tile 列表，表示推动链
        """
        chain, current = [], target.collision
        while current is not None:
            tile = target.gridmap.get_tile(current)
            if not tile.is_empty():
                chain.append(tile)
            if not(tile.has_prop('PUSH') or tile.has_prop('TEXT')):
                break
            current = target.action.get_neighbor_coord(current)
        return chain
    
    def generate_indirect_tile(self, target: 'TargetInteraction', chain: list) -> Optional['Tile']:
        """生成间接 tile（推动链中的间接影响部分）
        
        Args:
            target: TargetInteraction 实例
            chain: 推动链
        
        Returns:
            间接 tile 或 None
        """
        from base_gameLogic import Tile
        
        dir_tile = chain[0] if chain else None
        ind_tiles = chain[1:] if dir_tile else []
        coord = target.action.get_neighbor_coord(target.collision)
        if coord is None:
            return None
        entities = [ent for tile in ind_tiles for ent in tile.get_all_entities()]
        return Tile(coord, target.gridmap, entities)
    
    def create_summary(self, target: 'TargetInteraction', 
                      precomputed_key: Optional[str] = None,
                      updating: bool = True) -> Dict[str, Any]:
        """生成 TargetInteraction 的完整摘要
        
        Args:
            target: TargetInteraction 实例
            precomputed_key: 预计算的索引键（避免重复计算）
            updating: 是否模拟并存储到索引
        
        Returns:
            摘要字典
        """
        # 计算或使用预计算的索引
        if precomputed_key is None:
            target_key = self.compute_chain_index(target)
        else:
            target_key = precomputed_key
        
        # 检查缓存
        from recorder import Gridmap
        data_mgr = Gridmap.get_data_manager()
        cached = data_mgr.get_target(target_key)
        if cached is not None:
            return cached
        
        # 如果需要更新，使用 simulator 生成完整摘要
        if updating:
            summary_dict = self.target_simulator.simulate_and_store(target)
            data_mgr.set_target(target_key, summary_dict)
            return summary_dict
        
        # 否则返回简单摘要（不模拟）
        return {
            'target_key': target_key,
            'start': (int(target.start.x), int(target.start.y)),
            'action': target.action.name,
            'collision': (int(target.collision.x), int(target.collision.y)) if target.collision else None,
            'dist': target.dist
        }
    
    def get_or_create_hash(self, target: 'TargetInteraction', updating: bool = True) -> str:
        """获取或创建目标交互的哈希键
        
        Args:
            target: TargetInteraction 实例
            updating: 是否在缺失时创建并存储
        
        Returns:
            目标交互的哈希键
        """
        target_key = self.compute_chain_index(target)
        
        if updating:
            from recorder import Gridmap
            data_mgr = Gridmap.get_data_manager()
            if target_key not in data_mgr.target_manager:
                # 使用 TargetSimulator 模拟并存储
                summary = self.target_simulator.simulate_and_store(target)
                data_mgr.set_target(target_key, summary)
        
        return target_key
    
    def get_description(self, target: 'TargetInteraction') -> str:
        """生成目标交互的文字描述
        
        Args:
            target: TargetInteraction 实例
        
        Returns:
            描述字符串
        """
        text = f'Dist={target.dist}->{str(target.start)}->' if target.dir else 'Move'
        
        if target.dir:
            for entity in target.dir.get_all_entities():
                text += entity.get_description() + ' '
        if target.ind:
            text += '->'
            for entity in target.ind.get_all_entities():
                text += entity.get_description() + ' ' 
        return text
