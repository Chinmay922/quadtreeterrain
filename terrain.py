import collections
import random
import math
import time

import pyglet
import framebuffer
import glsl

import collision
import shapes
import vector

import time

RNDR_WIREFRAME, RNDR_SHADED = range(2)

class TerrainNode(object):
    """
    Quadtree node.
    """
    def __init__(self, x, y, size, type=0, level=0):
        self.level = level
        self.children = []
        self.type = type
        self.rect = shapes.AABB(x, y, size, size)    
        self.slope = 0.0
        self.slope_invert = False
        self.neighbor_mask = 0
        
    def combine(self):
        """
        Remove all descendants.
        """
        self.children = []
                
    def subdivide(self):
        """
        Split into four.
        """
        size = self.rect.width // 2
        self.children = [
            TerrainNode(self.rect.x, self.rect.y, size, self.type, self.level+1), 
            TerrainNode(self.rect.x + size, self.rect.y, size, self.type, self.level+1), 
            TerrainNode(self.rect.x, self.rect.y + size, size, self.type, self.level+1),
            TerrainNode(self.rect.x + size, self.rect.y + size, size, self.type, self.level+1),
        ]

    def simplify(self):
        """
        Check if all children are equivalent and childless. Combine them if so.
        """
        if not self.children: return
            
        if self.children[0].children or \
            self.children[1].children or \
            self.children[2].children or \
            self.children[3].children:
                return
            
        if self.children[0].type == \
            self.children[1].type == \
            self.children[2].type == \
            self.children[3].type:
                self.type = self.children[0].type
                # self.slope = 0
                self.combine()
                
        # TODO: check for slopes to simplify
        # \
        # . \               

class TerrainTree(object):
    """
    Quadtree that represents terrain
    """
    def __init__(self, x, y, size, min_node_size=None, max_level=None, type=0):
                
        if min_node_size and max_level:
            print "Cannot specify both min_node_size and max_level"
            pyglet.app.exit()
        elif min_node_size:
            self.min_node_size = min_node_size
            self.max_level = size // min_node_size
        elif max_level:
            self.max_level = max_level
            self.min_node_size = size // 2 ** max_level
        else:
            self.min_node_size = 8
            self.max_level = size // self.min_node_size
            
        self.root = TerrainNode(x, y, size, type)        
        self.num_types = 4
                
        # RENDERING
        self.tex = pyglet.resource.texture('red.png')
        self.fbchain = framebuffer.FramebufferChain(width=size, height=size)
        self.shaders = {        
            'basic': glsl.Shader(
                        # vert=file('shaders/terrain.vert').read(), 
                        frag=file('shaders/basic.frag').read()),        
            'blur_h': glsl.Shader(
                        # vert=file('shaders/terrain.vert').read(), 
                        frag=file('shaders/blur_h.frag').read()),
            'blur_v': glsl.Shader(
                        # vert=file('shaders/terrain.vert').read(), 
                        frag=file('shaders/blur_v.frag').read()),
            'threshold': glsl.Shader(
                        vert=file('shaders/pulse.vert').read(), 
                        frag=file('shaders/threshold.frag').read())
        }    
        with self.shaders['blur_h'] as shdr:
            shdr.uniformf('size', 1.0 / size)
        with self.shaders['blur_v'] as shdr:
            shdr.uniformf('size', 1.0 / size)
        
    def clear(self, type=0):        
        self.root.combine()
        self.root.type = type
                        
    def modify_quads_around_point(self, brush, type=0, node=None):
        """
        This is the main terrain deformation routine.
        """
        
        node = node or self.root
             
        # if node.type == type and not node.children: 
            # rect is already where it needs to be
            # return
                        
        if collision.rect_within_circle(node.rect, brush):
            # rect completely within circle
            node.combine()
            node.type = type
            node.slope = 0
                        
        elif collision.rect_vs_circle(node.rect, brush):
            # rect partially within circle
            if node.level >= self.max_level:
                self.find_slopes(node, brush, type)                
            else:
                if not node.children:
                    node.subdivide()
                for c in node.children:
                    self.modify_quads_around_point(brush, type, node=c)
                node.simplify()
                # self.find_slopes(node, brush, type)

    
    def find_slopes(self, node, brush, type):
        """
        Detect slopes
        """          
        if node.type == type: 
            return
        
        x = (node.rect.x - brush.x)
        y = (node.rect.y - brush.y)
        x_sq = x ** 2
        y_sq = y ** 2
        x2_sq = (node.rect.x2 - brush.x) ** 2
        y2_sq = (node.rect.y2 - brush.y) ** 2
        brush_r_sq = brush.radius**2

        # the x coordinate where the circle enters the bottom
        x_entry_bottom_sq = brush_r_sq - y_sq
        # the x coordinate where the circle enters the top
        x_entry_top_sq = brush_r_sq - y2_sq
        # the y coordinate where the circle enters the left
        y_entry_left_sq = brush_r_sq - x_sq
        # the y coordinate where the circle enters the right
        y_entry_right_sq = brush_r_sq - x2_sq

        if y < 0 and min(x_sq, x2_sq) < x_entry_bottom_sq < max(x_sq, x2_sq):
            if x < 0 and min(y_sq, y2_sq) < y_entry_left_sq < max(y_sq, y2_sq):
                node.type = type
                node.slope = -1
            if x > 0 and min(y_sq, y2_sq) < y_entry_right_sq < max(y_sq, y2_sq):
                node.type = type
                node.slope = 1
        if y > 0 and min(x_sq, x2_sq) < x_entry_top_sq < max(x_sq, x2_sq):
            if x < 0 and min(y_sq, y2_sq) < y_entry_left_sq < max(y_sq, y2_sq):
                node.type = type
                node.slope = 1
                node.slope_invert = True
            if x > 0 and min(y_sq, y2_sq) < y_entry_right_sq < max(y_sq, y2_sq):
                node.type = type
                node.slope = -1
                node.slope_invert = True
            
    def modify_slope(self, node):
        """
        Temporary function to cycle through the list of possible slopes for a node.
        """
        if node.slope == 0:
            node.slope = 1.0
            node.slope_invert = False
        elif node.slope == 1.0 and not node.slope_invert:
            node.slope = -1.0
            node.slope_invert = False
        elif node.slope == -1.0 and not node.slope_invert:
            node.slope = 1.0
            node.slope_invert = True
        elif node.slope == 1.0 and node.slope_invert:
            node.slope = -1.0
            node.slope_invert = True
        else:
            node.slope = 0.0
            node.slope_invert = False
            
    def collide_point(self, x, y, node=None):
                
        node = node or self.root
            
        if not node.children:
            return node
        else:
            tx, ty = (0, 0)
            if x >= node.rect.x + node.rect.width / 2: tx = 1
            if y >= node.rect.y + node.rect.height / 2: ty = 1
            idx = ty*2 + tx
            return self.collide_point(x, y, node=node.children[idx])

    def collide_circle(self, circle, node=None):
        """
        Collision detection helper that can recursively generate a list of nodes
        """
        node = node or self.root        
        nodes = []
        if collision.rect_vs_circle(node.rect, circle):
            if node.children:
                for c in node.children:
                    nodes += self.collide_circle(circle, node=c)
            elif node.type != 0:
                return [node]        
        return nodes
        
                                                    
    def draw(self, highlight=None, mode=0, node=None):
        """
        Draw all the nodes in the tree.
        """
        node = node or self.root
        node_stack = [node]
        vertices = [[],[],[],[]]
        # build world geometry
        # it might be nice to cache this on the gpu with a vbo        
        
        while node_stack:
            node = node_stack.pop()
            if node.children:
                node_stack += node.children
                continue            
            if node.type == 0:
                vertices[0] += node.rect.corners
            else:
                if node.slope == 0:
                    vertices[node.type] += node.rect.corners
                elif node.slope == 1 and not node.slope_invert:
                    vertices[node.type] += node.rect.corners[:6] + node.rect.corners[4:6]
                elif node.slope == -1 and not node.slope_invert:
                    vertices[node.type] += node.rect.corners[2:] + node.rect.corners[6:8]
                elif node.slope == 1 and node.slope_invert:
                    vertices[node.type] += node.rect.corners[4:] + node.rect.corners[:2] + node.rect.corners[:2]
                elif node.slope == -1 and node.slope_invert:
                    vertices[node.type] += node.rect.corners[6:] + node.rect.corners[:4] + node.rect.corners[2:4]
                  
        if mode == RNDR_SHADED: 
            
            # attach our framebuffer for rendering world geometry
            with self.fbchain as fb:              
                # render to fb  
                for type in range(self.num_types):                    
                    if type == 0: 
                        pyglet.gl.glColor3f(0, 0, 0)
                    else:
                        pyglet.gl.glColor3f(1, 1, 1)
                        
                    pyglet.graphics.draw(
                        len(vertices[type]) // 2, 
                        pyglet.gl.GL_QUADS, ('v2f', vertices[type]))
                        
            # perform 9x 9-tap gaussian blur                        
            for i in range(8):
                self.fbchain.draw_fb(shader=self.shaders['blur_h'])    
                self.fbchain.draw_fb(shader=self.shaders['blur_v'])
                    
            # draw the final fb to the default context
            with self.shaders['threshold'] as shader:
                shader.uniformf('time', time.clock())
                
            self.fbchain.draw(shader=self.shaders['threshold'])
            # self.fbchain.draw(shader=self.shaders['basic'])
            
        elif mode == RNDR_WIREFRAME:
                    
            # draw solids            
            for type in range(self.num_types):
                if type == 0: 
                    continue
                pyglet.gl.glColor3f(0.1 + type * 0.15, 0.1 + type * 0.15, 0.1 + type * 0.15)                            
                pyglet.graphics.draw(len(vertices[type]) // 2, pyglet.gl.GL_QUADS, ('v2f', vertices[type]))
                
            # switch to outline mode
            pyglet.gl.glPushAttrib(pyglet.gl.GL_POLYGON_BIT)
            pyglet.gl.glPolygonMode (pyglet.gl.GL_FRONT_AND_BACK, pyglet.gl.GL_LINE)
            for type in range(self.num_types):            
                pyglet.gl.glColor3f(0.2 + type * 0.2, 0.2 + type * 0.2, 0.2 + type * 0.2)
                pyglet.graphics.draw(len(vertices[type]) // 2, pyglet.gl.GL_QUADS, ('v2f', vertices[type]))
            pyglet.gl.glPopAttrib()
                    
        for h in highlight:
            # switch to outline mode
            pyglet.gl.glPushAttrib(pyglet.gl.GL_POLYGON_BIT)
            pyglet.gl.glPolygonMode (pyglet.gl.GL_FRONT_AND_BACK, pyglet.gl.GL_LINE)
            pyglet.gl.glColor3f(1.0, 0.5, 0.5)
            
            # draw outlines for highlighted quad
            pyglet.graphics.draw(4, pyglet.gl.GL_QUADS, ('v2f', h.rect.corners))
            pyglet.gl.glPopAttrib()