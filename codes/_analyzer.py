from ftplib import all_errors
from numpy.random import f
from recorder import Gridmap
from codes.base_gameLogic import Tile
from itertools import combinations
from collections import defaultdict
import heapq

class Community:
    def __init__(self, id, coords, example=None):

        self.id = id
        self.coords = coords
        self.example = example
    
    def neighbors(self):
        neighbors = set()
        for coord in self.coords:
            for neighbor in coord.neighbors:
                neighbors.add(neighbor)
        return neighbors
    
    def intercept(self, other):
        assert hasattr(other, 'coords')
        return self.coords.intersection(other.coords)
    
    def manhattan(self, other):
        distant = 0
        now = Community(-1, self.coords, self.example)
        while not now.intercept(other):
            distant += 1
            now = Community(-1, now.neighbors())
        return distant
    
    def is_empty(self):
        return self.example.is_empty()

    def __len__(self):
        return len(self.coords)
    
    def get_description(self):
        return f'Com{self.id} {self.example.get_description(False)} * {len(self)}'

    def __str__(self):
        return self.get_description()
    
    def __repr__(self):
        return self.get_description()

class CommunityGraph:

    def __init__(self, gridmap):
        self.gridmap = gridmap
        self.rebuild()

    def rebuild(self):
        self.nodes = self.get_communities()
        self.adj, self.man_dist = self.get_adjacency()
        self.cost_dist, self.path = self.get_distance()
    
    def get_community(self, item):
        if isinstance(item, int):
            return self.nodes[item]
        if isinstance(item, Tile):
            item = item.get_coord()
        for node in self.nodes:
            if item in node.coords:
                node.example = self.gridmap.get_tile(item)
                return node

    
    def get_communities(self):
        all_com, all_visited, id = [], set(), 0
        for coord, tile in self.gridmap.iter_tiles():
            if coord in all_visited:
                continue
           
            coords, visited, queue = {coord}, set(all_visited).union({coord}), [coord]

            while queue:
                current = queue.pop(0)
                for neighbor in current.neighbors:
                    if neighbor not in visited:
                        visited.add(neighbor)

                        if self.gridmap.get_tile(neighbor) == tile:
                            queue.append(neighbor)
                            coords.add(neighbor)

            if coords:
                all_visited.update(coords)
                community = Community(id, coords, tile)
                all_com.append(community)
                id += 1
        return all_com
    
    def get_adjacency(self):
        adjacency = defaultdict(dict)
        manhattan = defaultdict(dict)
        for com1, com2 in combinations(self.nodes, 2):
            man_dist = com1.manhattan(com2)
            manhattan[com1.id][com2.id] = man_dist
            manhattan[com2.id][com1.id] = man_dist
                
            if man_dist == 1:
                adjacency[com1.id][com2.id] =  man_dist
                adjacency[com2.id][com1.id] =  man_dist
        
        for com1 in self.nodes:
            manhattan[com1.id][com1.id] = float('inf')
        return adjacency, manhattan
    
    def get_distance(self):
        dist, path = defaultdict(dict), defaultdict(dict)
        for com1 in self.nodes:
            cur_dist, cur_path = self.get_distance_and_path(com1)
            dist[com1.id], path[com1.id] = cur_dist, cur_path
        return dist, path
    
    def get_distance_and_path(self, com1):
        dist = {com.id: float('inf') for com in self.nodes}
        parent = {com.id: None for com in self.nodes}
        all_path = {com.id: [] for com in self.nodes}

        pq = [(0, com1.id)]
        visited = set()

        while pq:
            cur_dist, cur_id = heapq.heappop(pq)
            if cur_id in visited:
                continue
            visited.add(cur_id)

            for neighbor in self.adj[cur_id]:
                if neighbor in visited:
                    continue

                weight = self.adj[cur_id][neighbor]
                new_dist = cur_dist + weight
                if new_dist < dist[neighbor]:
                    dist[neighbor] = new_dist
                    parent[neighbor] = [cur_id]
                    heapq.heappush(pq, (new_dist, neighbor))
                elif new_dist == dist[neighbor]:
                    parent[neighbor].append(cur_id)
        
        
        def dfs(cur, path, end):
            if cur == com1.id:
                all_path[end].append(path[::-1])
                return
            for pred in parent[cur]:
                if pred not in path:
                    dfs(pred, path + [pred], end)

        for com in self.nodes:
            if dist[com.id] != float('inf'):
                dfs(com.id, [com.id], com.id)

        return dist, all_path


class GridInfo:
    # 类级别的状态缓存（跨被试共享）
    _state_cache = {}
    _cache_hits = 0
    _cache_misses = 0

    def __init__(self, gridmap):
        self.gridmap = gridmap
        self.before, self.current, self.changes = None, self._collect_state(), None
        
        
    def rebuild(self, basic_info = None):
        self.before, self.current = self.current, self._collect_state()
        self.chain = basic_info['push_chain'] if basic_info else None
        self.changes = self._get_changes()
    
    @property
    def info(self):

        pre, cha = {}, {}
        # about rules
        pre['num_exist_rules'], cha['num_form_rules'], cha['num_break_rules'] = len(self.before['rules']), len(self.changes['add_rules']), len(self.changes['break_rules'])
        cha['bool_form_rules'], cha['bool_break_rules'] = cha['num_form_rules'] > 0, cha['num_break_rules'] > 0
        for prop in ['WIN', 'DEFEAT', 'PUSH', 'STOP', 'YOU']:
            pre[f'bool_has_{prop}_rule'] = prop in [rule.get_property().upper() for rule in self.before['rules']]
            cha[f'bool_form_{prop}_rule'] = prop in [rule.get_property().upper() for rule in self.changes['add_rules']]
            cha[f'bool_break_{prop}_rule'] = prop in [rule.get_property().upper() for rule in self.changes['break_rules']]

        # about objects
        loss_you = self.current['reachable'] == 0
        cha['bool_LOSS_YOU'], pre['bool_man_exist_YOU_object'] = loss_you, self.before['reachable'] > 0
        pre['num_reach_objects'], cha['num_change_reach_objects'] = self.before['reachable'], self.changes['reach_change']
        cha['bool_increase_reach_objects'], cha['bool_decrease_reach_objects'] = self.changes['reach_change'] > 0, self.changes['reach_change'] < 0 and not loss_you


        for prop in ['WIN', 'DEFEAT', 'PUSH', 'STOP', 'TEXT', 'REGULAR']:
            pre[f'num_man_{prop}_object'] = self.before['man_dist'][prop]
            pre[f'bool_man_exist_{prop}_object'] = self.before['man_dist'][prop] < float('inf')
            cha[f'bool_man_reachable_{prop}_object'] = self.before['man_dist'][prop] == float('inf') and self.changes['man_change'][prop] > 0
            cha[f'bool_man_unreachable_{prop}_object'] = self.current['man_dist'][prop] == float('inf') and self.changes['man_change'][prop] < 0 and not loss_you
            cha[f'float_man_for_{prop}_object'] = self.changes['man_change'][prop]
            cha[f'bool_man_approach_{prop}_object'] = self.changes['man_change'][prop] > 0
            cha[f'bool_man_avoid_{prop}_object'] = self.changes['man_change'][prop] < 0 and not loss_you

            pre[f'num_game_{prop}_object'] = self.before['game_dist'][prop]
            pre[f'bool_game_reach_{prop}_object'] = self.before['game_dist'][prop] < float('inf')
            cha[f'bool_game_reachable_{prop}_object'] = self.before['game_dist'][prop] == float('inf') and self.changes['game_change'][prop] > 0
            cha[f'bool_game_unreachable_{prop}_object'] = self.current['game_dist'][prop] == float('inf') and self.changes['game_change'][prop] < 0 and not loss_you
            cha[f'float_game_for_{prop}_object'] = self.changes['game_change'][prop]
            cha[f'bool_game_approach_{prop}_object'] = self.changes['game_change'][prop] > 0
            cha[f'bool_game_avoid_{prop}_object'] = self.changes['game_change'][prop] < 0 and not loss_you
        
        return {'pre': pre, 'cha': cha, 'inter': self.get_chain_info()}
    
    def get_final_chain(self, pre_chain):
        max_chain = max([len(c) for c in pre_chain])
        final_chain = [[] for _ in range(max_chain)]
        for cl in pre_chain:
            for i, c in enumerate(cl):
                final_chain[i].extend(c)
        return final_chain

    def get_chain_info(self):
        pre_chain, fea = [[c['pushed'] for c in ch['chain_list']] for ch in self.chain], {}
        chain = pre_chain[0] if len(pre_chain) == 1 else self.get_final_chain(pre_chain)
            
        fea['bool_interaction'] = bool(chain[0])
        fea['num_push'] = sum(len(c) for c in chain)
        fea['num_chain'] = sum([int(bool(c)) for c in chain])
        fea['bool_complex_push'] = fea['num_push'] > 1
        fea['bool_complex_chain'] = fea['num_chain'] > 1
        fea['bool_blocked'] = all([chain['chain_list'][-1]['blocked_by'] is not None for chain in self.chain])
        pushed = {'direct': chain[0], 'indirect': [e for c in chain[1:] for e in c]}
        for type, items in pushed.items():
            for prop in ['WIN', 'DEFEAT', 'PUSH', 'STOP', 'YOU', 'TEXT', 'REGULAR']:
                fea[f'bool_{type}_{prop}_inter'] = any(e.has_prop(prop) for e in items)
        return fea

  

    def _collect_state(self):
        """收集状态信息（带缓存）"""
        # 生成状态hash
        state_hash = self.gridmap._get_state_hash()
        
        # 检查缓存（完整状态缓存）
        if state_hash in GridInfo._state_cache:
            GridInfo._cache_hits += 1
            return GridInfo._state_cache[state_hash]
        
        GridInfo._cache_misses += 1
        
        # 缓存未命中，完整计算
        rules = self.gridmap.rule_manager.get_all_rules(rule_type = 'noun_is_property')
        num_object,man_dist, man_reach, num_reach, game_dist, game_reach, _, _ = self.gridmap._get_distances()
        
        result = {'rules': rules, 'objects': num_object, 'game_dist': game_dist, 'game_reach': game_reach, 
                  'man_dist': man_dist, 'man_reach': man_reach, 'reachable': num_reach}
        
        # 缓存结果
        GridInfo._state_cache[state_hash] = result
        return result
    
    @classmethod
    def get_cache_stats(cls):
        """获取GridInfo缓存统计"""
        total = cls._cache_hits + cls._cache_misses
        hit_rate = cls._cache_hits / total * 100 if total > 0 else 0
        return {
            'hits': cls._cache_hits,
            'misses': cls._cache_misses,
            'total': total,
            'hit_rate': f'{hit_rate:.2f}%',
            'cache_size': len(cls._state_cache)
        }
    
    @classmethod
    def clear_cache(cls):
        """清空GridInfo缓存"""
        cls._state_cache.clear()
        cls._cache_hits = 0
        cls._cache_misses = 0

    def _get_changes(self):
        add_rules = self.current['rules'] - self.before['rules']
        break_rules = self.before['rules'] - self.current['rules']
        man_change, game_change = {}, {}
        for key in self.current['man_reach']:
            man_change[key] = self.current['man_reach'][key] - self.before['man_reach'][key]
            game_change[key] = self.current['game_reach'][key] - self.before['game_reach'][key]
        reach_change = self.current['reachable'] - self.before['reachable']
        return {'add_rules': add_rules, 'break_rules': break_rules, 
                'man_change': man_change, 'game_change': game_change, 
                'reach_change': reach_change}


class Analysis(Gridmap):
    
    @classmethod
    def from_text(cls, text):
        analysis = super().from_text(text)
        analysis.load_observers()
        return analysis
    
    @classmethod
    def quick_load(cls, data):
        analysis = super().quick_load(data)
        analysis.load_observers()
        return analysis
    
    def load_observers(self, observers = ['com', 'info']):
        self.observers = {}
        for observer in observers:
            self.add_observer(observer)

    def add_observer(self, observer):
        if observer == 'com':
            self.observers['com'] = CommunityGraph(self)
        if observer == 'info':
            self.observers['info'] = GridInfo(self)


    def remove_observer(self, observer):
        self.observers.discard(observer)

    def update_observers(self, observer):
        if observer is None:
            for observer in self.observers:
                observer.rebuild()
        elif observer not in self.observers:
            self.add_observer(observer)
        else:
            self.observers[observer].rebuild()

    def get_observer(self, observer):
        # self.update_obervers(observer)
        return self.observers[observer]

    def get(self, observer, attr):
        if observer not in self.observers:
            self.add_observer(observer)
        # self.update_obervers(observer)
        if isinstance(attr, str):
            return getattr(self.observers[observer], attr)
        return [getattr(self.observers[observer], a) for a in attr]

    def step(self, action):

        new_grid, outcome, basic_info = super().step(action)
        self.observers['info'].rebuild(basic_info)
        return new_grid, outcome, basic_info
