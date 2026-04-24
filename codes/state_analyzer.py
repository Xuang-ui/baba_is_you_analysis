"""状态分析器 - 负责计算游戏状态的各种特征

将原本在 Gridmap 中的分析逻辑分离出来，符合单一职责原则。
"""

from typing import TYPE_CHECKING, Dict, List, Tuple
from util import Deque, PriorityQueue
from collections import deque
import hashlib
from base_gameLogic import GameOutcome, Action
from base_entity import Property, Material
from util import encoding, decoding

if TYPE_CHECKING:
    from recorder import State, Gridmap

MAX_DISTANCE_VALUE = 9999

class StateAnalyzer:
    """负责计算游戏状态的各种特征，只会暴力计算的"""
    
    PROP_KEYS = Property.VALIDLIST
    
    def __init__(self, state: 'State'):
        self.state = state
        self.key = state.key
        self.grid = state.rebuild()


    def get_agents(self):
        """检查 YOU 实体的位置"""
        return [you.get_coord().to_pair() for you in self.grid.get_entities_by_prop('YOU')]
    
    def get_outcome(self) -> GameOutcome:
        """检查当前游戏结果"""
        return self.grid.get_outcome()
    
    def get_props(self) -> List[int]:
        """获取每种属性的实体数量，EMPTY这里需要特别处理"""
        self.grid.entity_prop.rebuild()
        dic = {prop: len(v) for prop, v in self.grid.entity_prop.items()}
        dic['EMPTY'] = 0
        for _, tile in self.grid.iter_tiles():
            if tile.is_empty():
                dic['EMPTY'] += 1
        return dic
    
    def get_objects(self) -> List['str']:  
        """获取基本的实体统计信息"""
        self.grid.entity_id.rebuild()
        return {id: len(v) for id, v in self.grid.entity_id.items() if Material(id).is_object()}
        

    def get_tokens(self) -> Dict:
        """分析 token 规则的有效性"""
        token_ana = []
        visited = set()
        for rule in self.grid.rule_manager.read_valid_rules():
            token_ana.append(tuple(str(tok) for tok in rule.tokens))
            visited.update(rule.tokens)
        for token in self.grid.rule_manager.token_set - visited:
            token_ana.append(str(token))
        return token_ana
   
    def get_man_dist(self):
        """一次性计算 man_distance, game_distance 和 bound_distance"""
        all_you = self.grid.get_agent()
     
        man_dist_dict = {prop: MAX_DISTANCE_VALUE for prop in self.PROP_KEYS}

        if not all_you:
            return (man_dist_dict)
        
        you_coords = [you.get_coord() for you in all_you]
        # === BFS 1: Man Distance (所有邻居都传播) ===
        man_queue = Deque()
        man_visited = set()

        for coord in you_coords:
            man_queue.push((coord, 1))
            for prop in self.PROP_KEYS:
                if self.grid.get_tile(coord).has_prop(prop):
                    man_dist_dict[prop] = 0
        man_visited.update(you_coords)
        
        while not man_queue.isEmpty():
            coord, dist = man_queue.pop()
            for neighbor_coord in coord.neighbors:
                if neighbor_coord.bound or neighbor_coord in man_visited:
                    continue
                man_visited.add(neighbor_coord)
                neighbor_tile = self.grid.get_tile(neighbor_coord)
                man_queue.push((neighbor_coord, dist + 1))
                for prop in self.PROP_KEYS:
                    if neighbor_tile.has_prop(prop) and man_dist_dict[prop] > dist:
                        man_dist_dict[prop] = dist
        return man_dist_dict


    def get_game_dist(self):
        """获取可达位置及其游戏距离"""
        all_you = self.grid.get_agent()
        
        # 初始化结果字典
        game_dist_dict = {prop: MAX_DISTANCE_VALUE for prop in self.PROP_KEYS}
 
        if not all_you:
            return game_dist_dict

        you_coords = [you.get_coord() for you in all_you] 

        # === BFS 2: Game Distance (只有空格子传播) ===
        game_queue = Deque()
        game_visited = set()

        for coord in you_coords:
            game_queue.push((coord, 1))
            for prop in self.PROP_KEYS:
                if self.grid.get_tile(coord).has_prop(prop):
                    game_dist_dict[prop] = 0
        game_visited.update(you_coords)
        
        while not game_queue.isEmpty():
            coord, dist = game_queue.pop()
            for neighbor_coord in coord.neighbors:
                if neighbor_coord.bound or neighbor_coord in game_visited:
                    continue
                game_visited.add(neighbor_coord)
                neighbor_tile = self.grid.get_tile(neighbor_coord)
                
                if neighbor_tile.is_empty():
                    game_queue.push((neighbor_coord, dist + 1))

                for prop in self.PROP_KEYS:
                    if neighbor_tile.has_prop(prop) and game_dist_dict[prop] > dist:
                        game_dist_dict[prop] = dist
                    
        return game_dist_dict

    def get_bound_dist(self):
        """获取边界距离"""
        all_you = self.grid.get_agent()
        
        # 初始化结果字典
        bound_dist_dict = {prop: MAX_DISTANCE_VALUE for prop in self.PROP_KEYS}
 
        if not all_you:
            return bound_dist_dict

        you_coords = [you.get_coord() for you in all_you] 
        
        # === BFS 3: boundary_distance ===
        coord_cost = {}
        dq = deque()
        for coord in you_coords:
            coord_cost[coord] = 0
            dq.append(coord)
            tile0 = self.grid.get_tile(coord)
            for prop in StateAnalyzer.PROP_KEYS:
                if tile0.has_prop(prop):
                    bound_dist_dict[prop] = 0
        while dq:
            cur = dq.popleft()
            cur_cost = coord_cost[cur]
            for nb in cur.neighbors:
                if nb.bound:
                    continue
                nb_tile = self.grid.get_tile(nb)
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

        return bound_dist_dict
    
    def get_com_dist(self):
        """获取社区距离"""
    
        all_you = self.grid.get_agent()
        
        # 初始化结果字典
        com_dist_dict = {prop: MAX_DISTANCE_VALUE for prop in self.PROP_KEYS}
 
        if not all_you:
            return com_dist_dict
        
        # === BFS 4: community greedy distance ===
        from community_graph import CommunityGraph
        cg = CommunityGraph(self.grid) 
        yous = cg.get_community_by_prop('YOU')
        record = {prop: (float('inf'), 0) for prop in self.PROP_KEYS}
        for you in yous:
            for prop in self.PROP_KEYS:
                nd = []
                props = cg.get_community_by_prop(prop)
                if not props:
                    record[prop] = (float('inf'), 0)
                    continue
                for target in props:
                    nd.append((cg.dist[you][target], len(cg.path[you][target])))
                record[prop] = min(nd, key=lambda x: (x[0], -x[1]))
        com_dist_dict = {prop: round(min(x + 0.9**(y-1) - 1, MAX_DISTANCE_VALUE), 2) for prop, (x, y) in record.items()}

        return com_dist_dict
    
    def get_rules(self) -> Tuple[int, List]:
        """分析当前的规则"""
        record = {prop: [] for prop in self.PROP_KEYS}
        for n, p in self.grid.get_ruler('np').items():
            for prop in p.prop_lst:
                record[prop].append(n)
        return {k: tuple(sorted(v)) for k, v in record.items()}


    def sum_basic_features(self) -> Dict[str, any]:
        """计算基本特征汇总"""

        features = {
            'you': self.get_agents(),
            'outcome': self.get_outcome(),
            'rules': self.get_rules(),
            # 'tokens': self.get_tokens(),
            # 'objects': self.get_objects(),
            # 'prop': self.get_props(),
            # 'man_dist': self.get_man_dist(),
            # 'game_dist': self.get_game_dist(),
            # 'bound_dist': self.get_bound_dist(),
            # 'unit': self.get_plan_unit(),
        }
        return features
    

    def get_units(self):
        """获取游戏距离"""

        all_you = self.grid.get_agent()
        reachable_dict = {}   #trans_id: path

        if not all_you:
            return reachable_dict

        if len(all_you) == 1:
            return self._units_single_you(all_you[0])
        if len(all_you) > 1:
            # return self._units_multi_you(all_you)
            return self._units_multi_you(all_you)
    
    def _units_multi_you(self, yous):

        from recorder import State
        init_cooreds = tuple(you.get_coord() for you in yous)

        game_queue = Deque()
        game_visited = set()
        reachable = {}

        game_queue.push((init_cooreds, ''))
        game_visited.add(init_cooreds)

        pre_grid = self.grid.deep_copy()
        you_entities = pre_grid.get_agent()

        def place_all(coords):
            for i, c in enumerate(coords):
                pre_grid.move_entity(you_entities[i], c)
        
        while not game_queue.isEmpty():
            coords, path = game_queue.pop()
            coords_set = set(coords)
            
            place_all(coords)
            pre_state = self.state if len(path) == 0 else State(pre_grid)

            for action in (Action.up, Action.down, Action.left, Action.right):
                hit_non_empty = False
                next_coords = []

                for coord in coords:
                    nb = action.get_neighbor_coord(coord)

                    if nb.bound:
                        hit_non_empty = True
                        next_coords = None
                        break
                    tile = pre_grid.get_tile(nb)

                    if not tile.is_empty() and nb not in coords_set:
                        hit_non_empty = True
                        next_coords = None
                        break
                    
                    next_coords.append(nb)

                if hit_non_empty:
                    trans = pre_state.to_trans(action)
                    key = str(trans.key)
                    if key not in reachable:
                        reachable[key] = path + action.value

                if next_coords is not None:
                    nxt = tuple(next_coords)
                    if nxt not in game_visited:
                        game_visited.add(nxt)
                        game_queue.push((nxt, path + action.value))
            
        return reachable


    def _units_single_you(self, you):
        from recorder import State
        you_coord = you.get_coord()
        you_coords = [you_coord]
        game_queue = Deque()
        game_visited = set()
        reachable = {}
        game_queue.push((you_coord, ''))
        game_visited.add(you_coord)

        pre_grid = self.grid.deep_copy()
        you_entity = pre_grid.get_agent()[0]

        while not game_queue.isEmpty():
            coord, path = game_queue.pop()
            for action in (Action.up, Action.down, Action.left, Action.right):
                neighbor_coord = action.get_neighbor_coord(coord)

                if neighbor_coord.bound:
                    continue
                
                neighbor_tile = self.grid.get_tile(neighbor_coord)

                if not neighbor_tile.is_empty() and neighbor_coord not in you_coords:
                      
                    if path:
                        pre_grid.move_entity(you_entity, coord)  # 模拟可以重复用同一个模版
                        pre_state = State(pre_grid)
                    else:
                        pre_state = self.state

                    trans = pre_state.to_trans(action)  # 交给trans去模拟吧
                    key = str(trans.key)
                    if key not in reachable:
                        reachable[key] = path + action.value


                if neighbor_tile.is_empty() and neighbor_coord not in game_visited:
                    game_visited.add(neighbor_coord)
                    game_queue.push((neighbor_coord, path + action.value))

        return reachable

