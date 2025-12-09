from base_entity import Entity, EntityType, Coord

import numpy as np
from collections import defaultdict

class Token:
    def __init__(self, text, coord, rule=None):
        self.text, self.coord = text, coord
        self.rule = rule or []
        self.full = EntityType.TEXTDICT.get(self.text)

    def is_token(self):
        return self.text != ''
    
    def is_noun(self):
        return self.text in EntityType.NOUNDICT
    
    def is_property(self):
        return self.text in EntityType.PROPERTYDICT
    
    def is_attribute(self):
        return self.text in EntityType.ATTRIBUTEDICT
    
    def is_(self, txt):
        return self.full == txt
    
    def is_orphaned(self):
        return not self.rule
    
    def __hash__(self):
        return hash((self.text, self.coord))
    
    def __str__(self):
        return self.text

    def __repr__(self):
        text = f'{self.full}'
        # if self.rule is not None:
        #     for rule in self.rule:
        #         text += f' [{rule}]'
        return text
    
def entity_id_to_texture(entity_id):
    if entity_id in EntityType.NOUNDICT:
        name = EntityType.NOUNDICT[entity_id].lower()
        return f'en_rule_{name}.png'
    if entity_id.upper() in EntityType.NOUNDICT:
        name = EntityType.NOUNDICT[entity_id.upper()].lower()
        return f'en_normal_{name}.png'
    if entity_id in EntityType.PROPERTYDICT:
        name = EntityType.PROPERTYDICT[entity_id].lower()
        return f'en_attribute_{name}.png'
    if entity_id in EntityType.OPERATORDICT:
        name = EntityType.OPERATORDICT[entity_id].lower()
        return f'en_keyword_{name}.png'

class Rule:

    TYPE = ['noun_is_noun', 'noun_is_property']
    ACTIVE = {'noun_is_noun': False , 'noun_is_property': True}

    def __init__(self, rule_type, tokens=None):
        self.rule_type = rule_type
        self.is_active = True
        self.tokens = list(tokens) if tokens else []
        self.coord = [token.coord for token in self.tokens]
        [token.rule.append(self) for token in self.tokens]
    
    def get_property(self):
        if self.rule_type == 'noun_is_property' and self.is_active:
            return self.property
    
    def get_subject(self):
        if self.rule_type == 'noun_is_noun' and self.is_active:
            return self.noun1
        elif self.rule_type == 'noun_is_property' and self.is_active:
            return self.noun
        

    def get_description(self):
        pass

    def __str__(self):
        return self.get_description()
    
    def __repr__(self):
        return self.__str__()
    
    def __hash__(self):
        return hash(self.get_description())
    
    def __eq__(self, other):
        if not isinstance(other, Rule):
            return False
        return self.get_description() == other.get_description()
    
    
class NounIsNoun(Rule):
    def __init__(self, noun1, is_token, noun2):
        # delegate common token/coord handling to base class
        super().__init__('noun_is_noun', tokens=(noun1, is_token, noun2))
        self.noun1 = noun1.text
        self.noun2 = noun2.text
        self.is_active = Rule.ACTIVE['noun_is_noun']

    def get_description(self):
        noun1 = EntityType.NOUNDICT[self.noun1]
        noun2 = EntityType.NOUNDICT[self.noun2]
        return f"{noun1} is {noun2}"

class NounIsProperty(Rule):

    def __init__(self, noun, is_token, property):
        super().__init__('noun_is_property', tokens=(noun, is_token, property))
        self.is_active = Rule.ACTIVE['noun_is_property']
        self.noun = noun.text
        self.property = EntityType.PROPERTYDICT[property.text]

    def get_description(self):
        noun = EntityType.NOUNDICT[self.noun]
        return f"{noun} is {self.property}"


class RuleManager:
    def __init__(self, gridmap):
        self.gridmap = gridmap
        self.size = gridmap.get_size()
        self.rules = {rule_type: set() for rule_type in Rule.TYPE}
        self.update_rules()
    
    def get_all_rules(self, rule_type = None):
        if rule_type:
            return self.rules[rule_type]
        return set().union(*self.rules.values())

    def clear_rules(self):
        self.rules = {rule_type: set() for rule_type in Rule.TYPE}

    def update_rules(self):
        previous = self.get_all_rules()
        self.clear_rules()
        self.token_map, self.token_set = self._gen_token_map()
        self.token_dict = self._gen_token_dict()
        current = self.detect_all_rules()
        self.apply_all_rules()
        return previous, current, current - previous, previous - current
    
    def _gen_token_map(self):
        """Generate a 2D map of Token objects.

        Each entry is the Token instance returned by Tile.get_token(). The returned
        array has shape (height, width) and dtype=object so callers can access
        token.text and token.coord directly.
        """
        width, height = self.size
        # use object dtype to store Token objects
        token_map, token_set = np.empty((width, height), dtype=object), set()
        for x in range(width):
            for y in range(height):
                tok = self.gridmap.get_tile(self._pair_to_coord(x, y)).get_token()
                # Tile.get_token now returns a Token instance
                token_map[x, y] = tok
                if tok.is_token():

                    token_set.add(token_map[x, y])
        return token_map, token_set
    
    def _pair_to_coord(self, col, row):
        return Coord(col, self.size[1] - 1 - row)
    
    def _gen_token_dict(self):
        """Generate a dict mapping rows/cols to lists of token chains.

        Returns:
            token_dict: { 'r{row}': [ [Token,...], ... ], 'c{col}': [ [Token,...], ... ] }
        Each inner list is a contiguous chain of non-empty Token objects as returned
        by Tile.get_token(). The orientation preserves the existing coordinate
        convention used in _gen_token_map (token_map[height-1-y, x]).
        """
        width, height = self.size
        token_dict = {}

        # Rows
        for r in range(height):
            chains, cur_chain = [], []
            for x in range(width):
                tok = self.token_map[x, r]
                if tok.is_token():
                    cur_chain.append(tok)
                else:
                    chains.append(cur_chain)
                    cur_chain = []
            chains.append(cur_chain)
            token_dict['r' + str(height - 1 - r)] = [chain for chain in chains if chain]

        # Columns
        for c in range(width):
            chains, cur_chain = [], []
            for y in range(height):
                tok = self.token_map[c, y]
                if tok.is_token():
                    cur_chain.append(tok)
                else:
                    chains.append(cur_chain)
                    cur_chain = []
            chains.append(cur_chain)
            token_dict['c' + str(c)] = [chain for chain in chains if chain]
        return {key:val for key, val in token_dict.items() if val}

    def detect_all_rules(self):
        all_rules = set()
        for line in self.token_dict.values():
            for tokens in line:
                rules = self._rule_from_token(tokens)
                if rules is not None:
                    all_rules.update(rules)
        return all_rules
    
    def _rule_from_token(self, tokens):
        is_index = [i for i, token in enumerate(tokens) if token.is_('IS')]
        if not is_index:
            return None
        rules, current = set(), 0
        for is_pos in is_index:
            is_token = tokens[is_pos]
            left, right = tokens[current: is_pos][: : -1], tokens[is_pos + 1:]
            left_token, right_token, i, j = [], [], 0, 0
            if left and left[0].is_noun():
                left_token.append(left[0])
                while i+2 < len(left) and left[i+1].is_('AND') and left[i+2].is_noun():
                    left_token.append(left[i+2])
                    i += 2
            if right and right[0].is_attribute():
                right_token.append(right[0])
                while j+2 < len(right) and right[j+1].is_('AND') and right[j+2].is_attribute():
                    right_token.append(right[j+2])
                    j += 2
            if left_token and right_token:
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
        if right_token.is_property():
            rule = NounIsProperty(left_token, is_token, right_token)
            self.rules['noun_is_property'].add(rule)
        return rule
    
    def apply_all_rules(self):
        for rule_type, rules in self.rules.items():
            apply_func = getattr(self, f'_apply_{rule_type}')
            apply_func(rules)
    
    def _apply_noun_is_property(self, rules):
        for entity in self.gridmap.get_all_entities():
            entity.clear_prop()
        for rule in rules:
            if not rule.is_active:
                continue
            target_id = EntityType.noun2object(rule.noun)
            for entity in self.gridmap.get_entities_by_id(target_id):
                entity.add_prop(rule.property)
    
    def _apply_noun_is_noun(self, rules):
        all_noun2noun = defaultdict(list)
        for rule in rules:
            if not rule.is_active:
                continue
            all_noun2noun[rule.noun1].append(rule.noun2)
        to_be_removed = set()
        to_be_added = set()
        for noun1, noun2s in all_noun2noun.items():
            if not noun2s or noun1 in noun2s:
                continue
            target_id = EntityType.noun2object(noun1)
            target = self.gridmap.get_entities_by_id(target_id)
            to_be_removed.update(target)
            for entity in target:
                for noun2 in noun2s:
                    now_id = EntityType.noun2object(noun2)
                    to_be_added.add(Entity(now_id, entity.get_coord()))
        for entity in to_be_removed.copy():
            self.gridmap.remove_entity(entity)
        for entity in to_be_added.copy():
            self.gridmap.add_entity(entity)

    def __len__(self):
        return sum([len(rules) for rules in self.rules.values()])
    
    def __str__(self):
        string = f'RuleManager detect and apply {len(self)} rules\n'
        for _, rules in self.rules.items():
            for rule in rules:
                string += f'  {rule}\n'
        return string
