from PIL import Image, ImageChops, ImageEnhance, ImageDraw, ImageFont
import os
from base_entity import Material, Coord
from base_gameLogic import GameEngine, Action
from util import decoding
from collections import defaultdict

from typing import TYPE_CHECKING, Dict, Tuple, List, Optional
if TYPE_CHECKING:
    from recorder import State


class Graphic:

    ARROW = None

    def __init__(self, state: 'State', cell_size: int = 40, texture_path: str = 'texture', color = '#2b2b2b'):
        self.CELL_SIZE = cell_size
        self.TEXTURE_PATH = texture_path
        self.BACKGROUND_COLOR = color
        self.raw = decoding(state.raw)
        self._preload_figure()

    def __call__(self):
        return self.fig
   
    def _preload_figure(self):
        entities, (width, height) = self.raw[:-1], self.raw[-1]
        img_width, img_height = width * self.CELL_SIZE, height * self.CELL_SIZE
        self.fig = Image.new('RGB', (img_width, img_height), color=self.BACKGROUND_COLOR)
            # --- 新增：绘制灰色网格线 ---
        draw = ImageDraw.Draw(self.fig)
        grid_color = (60, 60, 60) # 稍浅一点的灰色，与背景 #bbbbbb 区分
        
        # 绘制纵线
        for x in range(0, img_width + 1, self.CELL_SIZE):
            draw.line([(x, 0), (x, img_height)], fill=grid_color, width=1)
        
        # 绘制横线
        for y in range(0, img_height + 1, self.CELL_SIZE):
            draw.line([(0, y), (img_width, y)], fill=grid_color, width=1)
        self.HEIGHT = height
        self.TEXTURE = {}
        draw_info = defaultdict(list)
        for (_, eid, _, x, y) in entities:
            draw_info[(x, y)].append(eid)
        for (x, y), draw_params in draw_info.items():
            self.fig = self._draw_one_tile(x, y, draw_params)

    def _draw_at(self, x, y, i=0, k=1):
        base_x, base_y = x * self.CELL_SIZE, (self.HEIGHT - 1 - y) * self.CELL_SIZE
        if k > 1:
            base_x += (i % k) * (self.CELL_SIZE // k)
            base_y += (i // k) * (self.CELL_SIZE // k)
        return int(base_x), int(base_y)
    
    def _eid_to_texture(self, eid, resize=1):
        eid = str(eid)

        if (eid, resize) in self.TEXTURE:
            return self.TEXTURE[(eid, resize)]
        
        if (eid, 1) in self.TEXTURE:
            img = self.TEXTURE[(eid, 1)].copy()
            img = img.resize((img.width // resize, img.height // resize), Image.Resampling.LANCZOS)
            self.TEXTURE[(eid, resize)] = img
            return img
        
        try:
            tex_file = Material(eid).texture
            full_path = os.path.join(self.TEXTURE_PATH, tex_file)
            if os.path.exists(full_path):
                img = Image.open(full_path).convert("RGBA")
                img = img.resize((self.CELL_SIZE, self.CELL_SIZE), Image.Resampling.LANCZOS)
                self.TEXTURE[(eid, resize)] = img
                return img
        except:
            raise FileNotFoundError(f"Texture for entity ID {eid} not found.")
        return None

    def _draw_one_tile(self, x, y, draw_params):

        k = min([k for k in range(10) if k**2 >= len(draw_params)])
        for i, entity in enumerate(draw_params):
            ex, ey = self._draw_at(x, y, i, k)
            tex = self._eid_to_texture(entity, resize=k)
            self.fig.paste(tex, (ex, ey), tex)
        return self.fig

    def _preload_arrows(self):  
        rotations = {'d': 90, 'w': 180, 'a': 270, 's': 0}
        arrow_path = os.path.join(self.TEXTURE_PATH, 'arrow.png')
        arrow = Image.open(arrow_path).convert("RGBA").resize((self.CELL_SIZE, self.CELL_SIZE), Image.Resampling.LANCZOS)
        self.ARROW = {}
        for dir, angle in rotations.items():
            self.ARROW[dir] = arrow.rotate(angle)
        
        undo_path = os.path.join(self.TEXTURE_PATH, 'undo.png')
        undo = Image.open(undo_path).convert("RGBA").resize((self.CELL_SIZE, self.CELL_SIZE), Image.Resampling.LANCZOS)
        self.ARROW['z'] = undo

        restart_path = os.path.join(self.TEXTURE_PATH, 'restart.png')
        restart = Image.open(restart_path).convert("RGBA").resize((self.CELL_SIZE, self.CELL_SIZE), Image.Resampling.LANCZOS)
        self.ARROW['r'] = restart


    def add_arrow(self, color, x, y, direction):
        if self.ARROW is None:
            self._preload_arrows()
        base_arrow = self.ARROW[direction]
        color_layer = Image.new('RGBA', base_arrow.size, color + (255,))
        self.fig.paste(color_layer, self._draw_at(x, y), base_arrow)
        return self.fig
    
    def add_path(self, path, color_from, color_to):
        if self.ARROW is None:
            self._preload_arrows()
        total_steps = len(path)
        for step, (x, y, d) in enumerate(path):
            arrow = self.ARROW[d]
            ratio = step / max(1, total_steps - 1)
            current_color = (
                int(color_from[0]*(1 - ratio) + color_to[0]*ratio),
                int(color_from[1]*(1 - ratio) + color_to[1]*ratio),
                int(color_from[2]*(1 - ratio) + color_to[2]*ratio)
            )
            color_layer = Image.new('RGBA', arrow.size, current_color + (255,))

            if d not in ['z', 'r']:
                post = Action(d).get_neighbor_coord((x, y))
                self.fig.paste(color_layer, self._draw_at(x, y), arrow)
            else:
                self.fig.paste(color_layer, self._draw_at(post.x, post.y), arrow)
        return self.fig
    @classmethod
    def grid_to_image(cls, grid, cell_size=40, texture_path='texture'):
        return cls(State(grid), cell_size, texture_path)


def grid_to_image(grid, cell_size=40, texture_path='texture', color = '#2b2b2b'):
    """将 grid 对象转换为 PIL Image"""
    img_width = grid.width * cell_size
    img_height = grid.height * cell_size
    fig = Image.new('RGB', (img_width, img_height), color=color)

    # --- 新增：绘制灰色网格线 ---
    draw = ImageDraw.Draw(fig)
    grid_color = (60, 60, 60) # 稍浅一点的灰色，与背景 #9b9b9b 区分
    
    # 绘制纵线
    for x in range(0, img_width + 1, cell_size):
        draw.line([(x, 0), (x, img_height)], fill=grid_color, width=1)
    
    # 绘制横线
    for y in range(0, img_height + 1, cell_size):
        draw.line([(0, y), (img_width, y)], fill=grid_color, width=1)

    raw_textures = {}
    for eid, _ in grid.entity_id.items():
        try:
            tex_file = Material(eid).texture
            full_path = os.path.join(texture_path, tex_file)
            if os.path.exists(full_path):
                raw_textures[eid] = Image.open(full_path).convert("RGBA")
        except:
            continue

    for (x, y), tile in grid.iter_tiles():
        
        entities = tile.get_all_entities()
        if not entities: continue

        draw_y = (grid.height - 1 - y) * cell_size
        draw_x = x * cell_size

        if len(entities) == 1:
            draw_params = [(entities[0].get_entity_id(), draw_x, draw_y, cell_size)]
        else:
            sub_size = cell_size // 2
            draw_params = []
            for i in range(min(len(entities), 4)):
                ex = draw_x + (i % 2) * sub_size
                ey = draw_y + (i // 2) * sub_size
                draw_params.append((entities[i].get_entity_id(), ex, ey, sub_size))

        for entity, ex, ey, esize in draw_params:
            tex = raw_textures[entity].resize((esize, esize), Image.Resampling.LANCZOS)
            fig.paste(tex, (int(ex), int(ey)), tex)
    # return fig
        # 装裱外框
    border = max(10, cell_size // 5)
    inner_border = max(1, border // 3)
    total = border + inner_border
    framed = Image.new('RGB', (img_width + 2 * total, img_height + 2 * total), color='#999999')
    frame_draw = ImageDraw.Draw(framed)
    # 外层深色边框
    frame_draw.rectangle([0, 0, framed.width - 1, framed.height - 1], outline='#666666', width=border)
    # 内层细亮线
    frame_draw.rectangle([border, border, framed.width - 1 - border, framed.height - 1 - border],
                            outline='#6a6a8e', width=inner_border)
    framed.paste(fig, (total, total))
    return framed

def grid_with_path(grid, path, cell_size=40, texture_path='texture', color='#2b2b2b'):
    """在 grid 图像上绘制路径箭头"""
    fig = grid_to_image(grid, cell_size, texture_path, color)
    if not path:
        return fig
    
    arrow = os.path.join(texture_path, 'arrow.png')
    if not os.path.exists(arrow):
        return fig
    
    rotations = {'d': 90, 'w': 180, 'a': 270, 's': 0}
    base_arrow = Image.open(arrow).convert("RGBA").resize((cell_size, cell_size), Image.Resampling.LANCZOS)

    total_steps = len(path)
    for step, (x, y, d) in enumerate(path):
        if d not in rotations:
            continue
        
        arrow = base_arrow.rotate(rotations[d])
        ratio = step / max(1, total_steps - 1)
        current_color = (int(0), int(255*ratio),int(255*(1 - ratio)))
        color_layer = Image.new('RGBA', arrow.size, current_color + (255,))
        # 6. 粘贴 (处理坐标转换)
        draw_x = x * cell_size
        draw_y = (grid.height - 1 - y) * cell_size
        fig.paste(color_layer, (int(draw_x), int(draw_y)), arrow)
        
    return fig

def grid_with_choice(grid, choice, threshold=0, cell_size=40, texture_path='texture', color='#2b2b2b'):
    """在 grid 图像上绘制选项箭头"""
    fig = grid_to_image(grid, cell_size, texture_path, color)
    if not choice:
        return fig
    
    arrow = os.path.join(texture_path, 'arrow.png')
    if not os.path.exists(arrow):
        return fig
    
    rotations = {'d': 90, 'w': 180, 'a': 270, 's': 0}
    base_arrow = Image.open(arrow).convert("RGBA").resize((cell_size, cell_size), Image.Resampling.LANCZOS)
    max_ratio = max(choice.values())
    total_ratios = sum(choice.values())

    for (x, y, d), ratio in choice.items():
        if d not in rotations or ratio < threshold:
            continue
        
        arrow = base_arrow.rotate(rotations[d])
        current_color = (int(255*(0.02+0.98*ratio/max_ratio)), int(0), int(0))

        color_layer = Image.new('RGBA', arrow.size, current_color + (256,))
        # 6. 粘贴 (处理坐标转换)
        draw_x = x * cell_size
        draw_y = (grid.height - 1 - y) * cell_size
        fig.paste(color_layer, (int(draw_x), int(draw_y)), arrow)

    # 在右上角绘制总数
    draw = ImageDraw.Draw(fig)
    font = ImageFont.truetype("arial.ttf", 20)
    draw.text((fig.width - 70, 70), f'visit:{total_ratios}', fill=(255, 255, 255), anchor='rt', font=font)
    return fig
