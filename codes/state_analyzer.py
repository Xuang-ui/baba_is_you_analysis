"""状态分析器 - 负责计算游戏状态的各种特征

将原本在 Gridmap 中的分析逻辑分离出来，符合单一职责原则。
"""

from typing import TYPE_CHECKING, Dict, List, Tuple
from util import Deque, PriorityQueue
from collections import deque

if TYPE_CHECKING:
    from recorder import Gridmap


class StateAnalyzer:
    """负责计算游戏状态的各种特征，只会暴力计算的"""
    
    PROP_KEYS = ['YOU', 'WIN', 'PUSH', 'DEFEAT', 'STOP', 'TEXT', 'REGULAR', 'EMPTY']
    
    @staticmethod
    def check_yous(grid: 'Gridmap'):
        """检查 YOU 实体的位置"""
        all_you = grid.get_entities_by_prop('YOU')
        return all_you[0].get_coord() if all_you else None
    
    @staticmethod
    def get_prop_counts(grid: 'Gridmap') -> List[int]:
        """获取每种属性的实体数量"""
        return {prop.lower(): len(grid.get_entities_by_prop(prop, False)) for prop in StateAnalyzer.PROP_KEYS}
    
    @staticmethod
    def get_basic_counts(grid: 'Gridmap') -> List['str']:
        """获取基本的实体统计信息"""
        id_set = {(entity.entity_id, entity.get_prop_one_hot()) for entity in grid.get_all_entities() if entity.is_object()}
        return {id:(len(grid.get_entities_by_id(id)),props) for id, props in id_set}

    
    @staticmethod
    def get_token_counts(grid: 'Gridmap') -> Dict:
        """分析 token 规则的有效性"""
        tokens = grid.rule_manager.token_set
        token_lst = sorted(tokens, key=lambda x: (-len(x.rule), -x.coord.y, x.coord.x))
        visited, cur, token_ana = set(), '', {'Valid': [], 'Invalid': []}

        def expand_token(token, cur, visited):
            for rule in token.rule:
                for token in rule.tokens:
                    if token not in visited:
                        visited.add(token)
                        cur += str(token)
                        cur, visited = expand_token(token, cur, visited)
            return cur, visited
        
        for token in token_lst:
            if token in visited:
                continue
            if not token.rule:
                token_ana['Invalid'].append(str(token))
                visited.add(token)
                continue
            cur, visited = expand_token(token, '', visited)
            token_ana['Valid'].append(cur)
        return {key:tuple(sorted(token_ana[key])) for key in token_ana}
    
    @staticmethod
    def get_distances(grid: 'Gridmap') -> Tuple:
        """一次性计算 man_distance, game_distance 和 bound_distance"""
        all_you = grid.get_entities_by_prop('YOU')
        num_objects = len(grid.get_all_entities())
        you_coords = [you.get_coord() for you in all_you]
        
        # 初始化结果字典
        man_dist_dict = {prop: float('inf') for prop in StateAnalyzer.PROP_KEYS}
        game_dist_dict = {prop: float('inf') for prop in StateAnalyzer.PROP_KEYS}
        bound_dist_dict = {prop: float('inf') for prop in StateAnalyzer.PROP_KEYS}

        if not all_you:
            # 没有 YOU 对象时，返回默认值
            man_reach_dict = {prop: 0 for prop in StateAnalyzer.PROP_KEYS}
            game_reach_dict = {prop: 0 for prop in StateAnalyzer.PROP_KEYS}
            bound_reach_dict = {prop: 0 for prop in StateAnalyzer.PROP_KEYS}
            return (num_objects, man_dist_dict, man_reach_dict, {(0, float('inf'))}, game_dist_dict, game_reach_dict, bound_dist_dict, bound_reach_dict)

        # === BFS 1: Man Distance (所有邻居都传播) ===
        man_queue = Deque()
        man_visited = set()

        for coord in you_coords:
            man_queue.push((coord, 1))
            for prop in StateAnalyzer.PROP_KEYS:
                if grid.get_tile(coord).has_prop(prop):
                    man_dist_dict[prop] = 0
        man_visited.update(you_coords)
        
        while not man_queue.isEmpty():
            coord, dist = man_queue.pop()
            for neighbor_coord in coord.neighbors:
                if neighbor_coord.bound or neighbor_coord in man_visited:
                    continue
                man_visited.add(neighbor_coord)
                neighbor_tile = grid.get_tile(neighbor_coord)
                man_queue.push((neighbor_coord, dist + 1))
                for prop in StateAnalyzer.PROP_KEYS:
                    if neighbor_tile.has_prop(prop) and man_dist_dict[prop] > dist:
                        man_dist_dict[prop] = dist
        
        # === BFS 2: Game Distance (只有空格子传播) ===
        game_queue = Deque()
        game_visited = set()
        reachable = set()

        for coord in you_coords:
            game_queue.push((coord, 1))
            for prop in StateAnalyzer.PROP_KEYS:
                if grid.get_tile(coord).has_prop(prop):
                    game_dist_dict[prop] = 0
        game_visited.update(you_coords)
        reachable.update([(str(coord), 0) for coord in you_coords])
        
        while not game_queue.isEmpty():
            coord, dist = game_queue.pop()
            for neighbor_coord in coord.neighbors:
                if neighbor_coord.bound or neighbor_coord in game_visited:
                    continue
                game_visited.add(neighbor_coord)
                neighbor_tile = grid.get_tile(neighbor_coord)
                
                if neighbor_tile.is_empty():
                    game_queue.push((neighbor_coord, dist + 1))
                else:
                    reachable.add((str(neighbor_coord), dist))

                for prop in StateAnalyzer.PROP_KEYS:
                    if neighbor_tile.has_prop(prop) and game_dist_dict[prop] > dist:
                        game_dist_dict[prop] = dist
        
        # === BFS 3: boundary_distance ===
        coord_cost = {}
        dq = deque()
        for coord in you_coords:
            coord_cost[coord] = 0
            dq.append(coord)
            tile0 = grid.get_tile(coord)
            for prop in StateAnalyzer.PROP_KEYS:
                if tile0.has_prop(prop):
                    bound_dist_dict[prop] = 0
        while dq:
            cur = dq.popleft()
            cur_cost = coord_cost[cur]
            for nb in cur.neighbors:
                if nb.bound:
                    continue
                nb_tile = grid.get_tile(nb)
                add_cost = 0 if nb_tile.is_empty() else 1
                new_cost = cur_cost + add_cost
                prev_cost = coord_cost.get(nb, float('inf'))
                if new_cost < prev_cost:
                    coord_cost[nb] = new_cost
                    if add_cost == 0:
                        dq.appendleft(nb)
                    else:
                        dq.append(nb)
                    for prop in StateAnalyzer.PROP_KEYS:
                        if nb_tile.has_prop(prop) and bound_dist_dict[prop] > new_cost:
                            bound_dist_dict[prop] = new_cost

        # 计算 reach 值
        man_reach_dict = {prop: 1/(1+dist) for prop, dist in man_dist_dict.items()}
        game_reach_dict = {prop: 1/(1+dist) for prop, dist in game_dist_dict.items()}
        bound_reach_dict = {prop: 1/(1+dist) for prop, dist in bound_dist_dict.items()}
        
        reachable = {coord: dist for coord, dist in sorted(reachable, key=lambda x: (x[1]))}
        return (num_objects, man_dist_dict, man_reach_dict, reachable, game_dist_dict, game_reach_dict, bound_dist_dict, bound_reach_dict)
    
    @staticmethod
    def get_man_distance(grid: 'Gridmap'):
        """获取曼哈顿距离"""
        num_objects, man_dist, man_reach, _, _, _, _, _ = StateAnalyzer.get_distances(grid)
        return num_objects, man_dist, man_reach

    @staticmethod
    def get_game_distance(grid: 'Gridmap'):
        """获取游戏距离"""
        _, _, _, reachable_count, game_dist, game_reach, _, _ = StateAnalyzer.get_distances(grid)
        return reachable_count, game_dist, game_reach
    
    @staticmethod
    def get_rules(grid: 'Gridmap') -> Tuple[int, List]:
        """分析当前的规则"""
        rules = grid.rule_manager.get_all_rules(rule_type='noun_is_property')
        rule_count = {prop: [] for prop in StateAnalyzer.PROP_KEYS}
        for rule in rules:
            cur_prop = rule.get_property().upper()
            cur_object = rule.get_subject().upper()
            rule_count[cur_prop].append(cur_object)
        return {prop.lower(): rule_count[prop] for prop in StateAnalyzer.PROP_KEYS}
    
    @staticmethod
    def get_greedy_community(grid: 'Gridmap') -> List[float]:
        """计算基于社区图的贪心距离"""
        from community_graph import CommunityGraph
        
        cg = CommunityGraph(grid)
        yous = cg.get_community_by_prop('YOU')
        if not yous:
            return [float('inf')] * len(StateAnalyzer.PROP_KEYS)
        
        record = []
        for you in yous:
            for prop in StateAnalyzer.PROP_KEYS:
                nd = []
                props = cg.get_community_by_prop(prop)
                if not props:
                    record.append((float('inf'), 0))
                    continue
                for target in props:
                    nd.append((cg.dist[you][target], len(cg.path[you][target])))
                record.append(min(nd, key=lambda x: (x[0], -x[1])))
        return [x + 0.9**(y-1) - 1 for x, y in record]
