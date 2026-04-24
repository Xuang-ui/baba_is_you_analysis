"""
交互式 Baba Is You 游戏界面
用法: python play_interactive.py
启动后输入地图名(如 intro)加载, 按 WASD 移动, R 重启, Z 撤销
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import tkinter as tk
from PIL import Image, ImageTk, ImageDraw, ImageFont
from mdpframework import Environment
from recorder import Gridmap
from base_gameLogic import Action, GameEngine
from state_graphic import grid_to_image
from recorder import get_data_manager


class GameApp:
    CELL_SIZE = 48
    TEXTURE_PATH = os.path.join(os.path.dirname(__file__), 'texture')
    ACTION_SYMBOLS = {'w': '↑', 's': '↓', 'a': '←', 'd': '→', 'z': '↶', 'r': '↻'}

    def __init__(self):
        self.env = Environment(engine = GameEngine)

        self.root = tk.Tk()
        self.root.title('Baba Is You - Interactive')
        self.root.configure(bg='#1a1a2e')

        # 顶部：地图输入
        top = tk.Frame(self.root, bg='#1a1a2e')
        top.pack(pady=8)
        tk.Label(top, text='Map:', bg='#1a1a2e', fg='white', font=('Consolas', 14)).pack(side=tk.LEFT)
        self.map_entry = tk.Entry(top, width=15, font=('Consolas', 14))
        self.map_entry.pack(side=tk.LEFT, padx=4)
        self.map_entry.insert(0, 'tutorial')
        self.map_entry.bind('<Return>', lambda e: self._load_map())
        tk.Button(top, text='Load', command=self._load_map, font=('Consolas', 12)).pack(side=tk.LEFT, padx=4)

        # 状态栏
        self.status_var = tk.StringVar(value='输入地图名后按 Enter 或 Load 加载')
        tk.Label(self.root, textvariable=self.status_var, bg='#1a1a2e', fg='#aaaaaa',
                 font=('Consolas', 11)).pack()

        # 画布
        self.canvas = tk.Canvas(self.root, bg='#2b2b2b', highlightthickness=0)
        self.canvas.pack(padx=10, pady=10)

        # 键盘绑定
        self.root.bind('<Key>', self._on_key)
        self.root.focus_set()

    def _load_map(self):
        map_name = self.map_entry.get().strip()

        try:
            self.env.load_map(map_name)
            self._render()
            self.status_var.set(f'地图 "{map_name}" 已加载  |  WASD 移动  R 重启  Z 撤销')
        except Exception as e:
            self.status_var.set(f'加载失败: {e}')

    def _on_key(self, event):
        key = event.char.lower() if event.char else ''

        if key in self.env.grid.get_possible_actions():
            self.env.step(key)
            self._render()
            self.status_var.set(f'上次操作: {self.ACTION_SYMBOLS.get(key, key)}  |  结果: {self.env.outcome}  |  WASD 移动  R 重启  Z 撤销')

    def _render(self):
        img = grid_to_image(self.env.grid, cell_size=self.CELL_SIZE, texture_path=self.TEXTURE_PATH)
        self._tk_img = ImageTk.PhotoImage(img)
        self.canvas.config(width=img.width, height=img.height)
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self._tk_img)

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    GameApp().run()
