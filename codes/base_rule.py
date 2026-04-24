from base_entity import Entity, Material, Coord, Property

import numpy as np
from collections import defaultdict
from itertools import product
from collections import defaultdict

class Token(Material):

    def __init__(self, text, coord, rule=None):
        super().__init__(text)
        self.coord = coord
        self.rule = rule or []

    def is_token(self): return not self.is_special()
    def is_(self, txt): return self.full_name == txt
    def is_orphaned(self): return not self.rule 
    def get_coord(self): return self.coord
    
    def __hash__(self):
        return hash((self.full_name, self.coord))
    
    def __eq__(self, other):
        return self.full_name == other.full_name and self.coord == other.coord

class Rule:

    TYPE = ['noun_is_noun', 'noun_is_property']
    ACTIVE = {'noun_is_noun': False , 'noun_is_property': True}

    def __init__(self, rule_type, tokens=None):
        self.rule_type = rule_type
        self.tokens = list(tokens) if tokens else []
        self.coord = [token.get_coord() for token in self.tokens]
        [token.rule.append(self) for token in self.tokens]
    
    def get_property(self):
        if self.rule_type == 'noun_is_property' and self.is_active:
            return self.property
    
    def get_subject(self):
        if self.rule_type == 'noun_is_noun' and self.is_active:
            return self.noun1
        elif self.rule_type == 'noun_is_property' and self.is_active:
            return self.noun
        
    def __repr__(self):
        return ' '.join([tok.full_name for tok in self.tokens])
    
    def __hash__(self):
        return hash(self.__repr__())
    
    def __eq__(self, other):
        if not isinstance(other, Rule):
            return False
        return self.__repr__() == other.__repr__()
    
    
class NounIsNoun(Rule):
    def __init__(self, noun1, is_token, noun2):
        # delegate common token/coord handling to base class
        super().__init__('noun_is_noun', tokens=(noun1, is_token, noun2))
        self.noun1 = noun1
        self.noun2 = noun2
        self.is_active = Rule.ACTIVE['noun_is_noun']

    def get_description(self):
        return f"{self.noun1} IS {self.noun2}"

class NounIsProperty(Rule):

    def __init__(self, noun, is_token, property):
        super().__init__('noun_is_property', tokens=(noun, is_token, property))
        self.is_active = Rule.ACTIVE['noun_is_property']
        self.noun = noun
        self.property = property


class RuleManager:
    def __init__(self, gridmap):
        self.gridmap = gridmap
        self.size = gridmap.get_size()
        self.rules = defaultdict(set)
        self._rule_dirty = True

        self.manager = {'np': defaultdict(Property), 'nn': defaultdict(list)}
        self.memory = self.record_memory()
        self.update_all_rules()

    def mark_dirty(self): self._rule_dirty = True
    def clear_all_rules(self): 
        self.mark_dirty()
        self.rules = defaultdict(set)    
        for m in self.manager.values():
            m.clear()
    
    def update_all_rules(self):        
        self.get_all_rules()
        self.apply_all_rules()

    def get_all_rules(self, rule_type = None):
        if self._rule_dirty:
            self.detect_all_rules()
        if rule_type:
            return self.rules[rule_type]
        return self.read_all_rules()   

    def detect_all_rules(self):
        self.token_map, self.token_set = self._gen_token_map()
        self.token_dict = self._gen_token_dict()
        self.clear_all_rules()
        for line in self.token_dict.values():
            for tokens in line:
                self._rule_from_token(tokens)
        self._rule_dirty = False

    def read_all_rules(self): 
        return [rule for v in self.rules.values() for rule in v]
    
    def read_valid_rules(self):
        return [rule for r, v in self.rules.items() if Rule.ACTIVE[r] for rule in v]
    
    def apply_all_rules(self):
        for rule_type in self.rules.keys():
            if Rule.ACTIVE[rule_type]:
                getattr(self, f'_apply_{rule_type}')()
        self.memory = self.record_memory()

    def record_memory(self):
        np_copy = defaultdict(Property)
        nn_copy = defaultdict(list)
        for k, v in self.manager['np'].items():
            np_copy[k] = Property(v._flag)
        for k, v in self.manager['nn'].items():
            nn_copy[k] = v.copy()
        return {'np': np_copy, 'nn': nn_copy}
    
    
    # ====== 预先计算的token地图 ======
    def coord(self, col, row):
        """游戏中规则的识别是沿着x轴递增和y轴递减的方向，这里统一一下"""
        return Coord((col, self.size[1] - 1 - row), self.size)
    
    def _gen_token_map(self):

        width, height = self.size
        token_map, token_set = np.empty((width, height), dtype='U3'), set()
        for x in range(width):
            for y in range(height):
                tok = self.gridmap.get_tile(self.coord(x, y)).get_token()
                token_map[x, y] = tok
                if len(tok) > 0:
                    token_set.update(Token(t, self.coord(x, y)) for t in tok)
        return token_map, token_set
    
    @staticmethod
    def _product(cur_chain):
        if all(len(toks) == 1 for toks in cur_chain):
            return [[toks[0] for toks in cur_chain]]
        return list(product(*cur_chain))

    def _gen_token_dict(self):

        width, height = self.size
        token_dict = {}

        # Rows
        for r in range(height):
            row = self.token_map[:, r]
            valid_tokens = np.where(row != '')[0]
            
            # need at least 3 tokens to form a rule
            if len(valid_tokens) <= 2: 
                continue

            chains, cur_chain = [], []
            last_x = -2
            for cur_x in valid_tokens:
                toks = [(t, cur_x) for t in row[cur_x]]
                if cur_x == last_x + 1:
                    cur_chain.append(toks)
                else:
                    if len(cur_chain) >= 3:
                        chains += self._product(cur_chain)
                    cur_chain = [toks]
                last_x = cur_x
            if len(cur_chain) >= 3: 
                chains += self._product(cur_chain)
            
            if chains:
                token_chain = [[Token(t, self.coord(x, r)) for t, x in comb] for comb in chains]
                token_dict['r' + str(height - 1 - r)] = token_chain

        # Columns
        for c in range(width):
            col = self.token_map[c, :]
            valid_tokens = np.where(col != '')[0]

            if len(valid_tokens) <= 2:
                continue

            chains, cur_chain = [], []
            last_y = -2
            for cur_y in valid_tokens:
                toks = [(t, cur_y) for t in col[cur_y]]
                if cur_y == last_y + 1:
                    cur_chain.append(toks)
                else:
                    if len(cur_chain) >= 3:
                        chains += self._product(cur_chain)
                    cur_chain = [toks]
                last_y = cur_y
            if len(cur_chain) >= 3:
                chains += self._product(cur_chain)
            
            if chains:
                token_chain = [[Token(t, self.coord(c, y)) for t, y in comb] for comb in chains]
                token_dict['c' + str(c)] = token_chain

        return token_dict

    # ====== 规则检测 ======

    def _rule_from_token(self, tokens):

        is_index = [(i, token) for i, token in enumerate(tokens) if token.is_('IS')]
        if not is_index:
            return set()
        
        rules, current = set(), 0
        for is_pos, is_token in is_index:

            left, right = tokens[current: is_pos][: : -1], tokens[is_pos + 1:]
            left_token, right_token, i, j = [], [], 0, 0

            if left and left[0].is_noun():
                left_token.append(left[0])

                while i+2 < len(left) and left[i+1].is_('AND') and left[i+2].is_noun():
                    left_token.append(left[i+2])
                    i += 2
            if not left_token:
                current = is_pos + 1
                continue

            if right and right[0].is_attribute():
                right_token.append(right[0])

                while j+2 < len(right) and right[j+1].is_('AND') and right[j+2].is_attribute():
                    right_token.append(right[j+2])
                    j += 2
            if not right_token:
                current = is_pos + 1
                continue
        
            for left in left_token:
                for right in right_token:
                    rules.add(self._add_is_rule(left, is_token, right))
            current = is_pos + 1

        return rules

    def _add_is_rule(self, left_token, is_token, right_token):
        assert left_token.is_noun() and right_token.is_attribute()

        if right_token.is_noun():
            rule = NounIsNoun(left_token, is_token, right_token)
            self.rules['noun_is_noun'].add(rule)
            self.manager['nn'][left_token.to_object()].append(right_token.to_object())

        if right_token.is_property():
            rule = NounIsProperty(left_token, is_token, right_token)
            self.rules['noun_is_property'].add(rule)
            self.manager['np'][left_token.to_object()].add(right_token.full_name)
        return rule
    
    # ====== 规则应用 ======

    def _apply_noun_is_property(self):
        past_rule = self.memory.get('np', defaultdict(Property))
        cur_rule = self.manager.get('np', defaultdict(Property))

        for k in set(past_rule.keys()) | set(cur_rule.keys()):
            if past_rule[k] != cur_rule[k]:
                self.gridmap.mark_dirty('entity_prop')
                for entity in self.gridmap.get_entities_by_id(k):
                    entity.mark_prop_dirty()
    
    def _apply_noun_is_noun(self):
        
        to_be_removed, to_be_added = [], []
        for bef, aft in self.manager['nn'].items():
            if bef in aft:
                continue
            for ent_b in self.gridmap.get_entities_by_id(bef):
                to_be_removed.append(ent_b)
                for id_a in aft:
                    to_be_added.append(ent_b.trans_id(id_a))
        if len(to_be_removed) + len(to_be_added) > 0:
            self.gridmap.mark_dirty('entity_id')

        for ent in to_be_removed:
            self.gridmap.remove_entity(ent)
        for ent in to_be_added:
            self.gridmap.add_entity(ent)

    def __len__(self):
        return sum([len(rules) for rules in self.rules.values()])
    
    def __str__(self):
        string = f'RuleManager detect and apply {len(self)} rules\n'
        for _, rules in self.rules.items():
            for rule in rules:
                string += f'  {rule}\n'
        return string
