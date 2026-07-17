"""
Jopex Light Studio
Professional Lighting Addon for Blender
Developed by Jopex Creatives
Contact: jopexcreatives@gmail.com
Version: 1.0.0
© 2025 Jopex Creatives. All Rights Reserved.
"""

bl_info = {
    "name": "Jopex Light Studio",
    "author": "Jopex Creatives",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Jopex Light Studio",
    "description": "Professional lighting addon with quick presets, rig control, and master controls",
    "category": "Lighting",
}

import bpy
import math
import json
import os
import bpy.utils.previews
import bmesh
from bpy.types import Panel, Operator, PropertyGroup, Menu
from bpy.props import (
    IntProperty, FloatProperty, BoolProperty, 
    EnumProperty, PointerProperty, StringProperty,
    FloatVectorProperty, CollectionProperty
)
from mathutils import Vector
from bpy.app.handlers import persistent

# ==============================================
# GLOBAL VARIABLES
# ==============================================

custom_icons = None

def refresh_ui():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

@persistent
def load_post_handler(dummy):
    refresh_ui()

@persistent
def scene_update_post_handler(scene, depsgraph):
    try:
        settings = scene.jopex_settings
        
        if settings.product_object and settings.product_object.name not in bpy.data.objects:
            settings.product_object = None
            refresh_ui()
            
        scene_lights = [obj for obj in scene.objects if obj.type == 'LIGHT' and obj.get("jopex_light", False)]
        existing_in_settings = [ls.name for ls in settings.lights]
        
        changed = False
        for i in range(len(settings.lights)-1, -1, -1):
            if settings.lights[i].name not in [obj.name for obj in scene_lights]:
                settings.lights.remove(i)
                changed = True
                
        for light_obj in scene_lights:
            if light_obj.name not in existing_in_settings:
                ls = settings.lights.add()
                ls.name = light_obj.name
                ls.light_type = light_obj.data.type
                ls.power = light_obj.data.energy
                light_obj.show_name = True
                changed = True
                
        if changed:
            refresh_ui()
    except Exception as e:
        pass

# ==============================================
# UTILITY FUNCTIONS
# ==============================================

def get_bbox_center(obj):
    if not obj:
        return Vector((0, 0, 0))
    
    matrix = obj.matrix_world
    corners = [matrix @ Vector(corner) for corner in obj.bound_box]
    
    min_x = min(c.x for c in corners)
    min_y = min(c.y for c in corners)
    min_z = min(c.z for c in corners)
    max_x = max(c.x for c in corners)
    max_y = max(c.y for c in corners)
    max_z = max(c.z for c in corners)
    
    return Vector(((min_x + max_x) / 2, (min_y + max_y) / 2, (min_z + max_z) / 2))

def get_object_size(obj):
    if not obj:
        return 1.0
    
    matrix = obj.matrix_world
    corners = [matrix @ Vector(corner) for corner in obj.bound_box]
    
    min_co = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    max_co = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    
    dimensions = max_co - min_co
    return max(dimensions.x, dimensions.y, dimensions.z)

def clear_jopex_lights():
    lights_to_remove = []
    for obj in bpy.data.objects:
        if obj.type == 'LIGHT' and obj.get("jopex_light", False):
            lights_to_remove.append(obj)
    
    for light in lights_to_remove:
        bpy.data.objects.remove(light, do_unlink=True)
    
    # Also remove the rig
    rig = bpy.data.objects.get("Jopex_Lighting_Rig")
    if rig:
        bpy.data.objects.remove(rig, do_unlink=True)
    
    # Also remove volume
    volume = bpy.data.objects.get("Jopex_Volume")
    if volume:
        bpy.data.objects.remove(volume, do_unlink=True)

def create_lighting_rig(context):
    target_name = "Jopex_Lighting_Rig"
    
    if target_name in bpy.data.objects:
        target = bpy.data.objects[target_name]
        target.show_in_front = True
        settings = context.scene.jopex_settings
        target.empty_display_size = 0.3 * settings.master_scale
        return target
    
    empty_data = None
    target = bpy.data.objects.new(target_name, empty_data)
    target.empty_display_type = 'SPHERE'
    target.empty_display_size = 0.3
    target.show_in_front = True
    target.location = (0, 0, 0)
    context.scene.collection.objects.link(target)
    return target

def create_volume_object(context):
    """Create a volume object around the scene"""
    volume_name = "Jopex_Volume"
    
    # Remove existing volume if exists
    if volume_name in bpy.data.objects:
        old_volume = bpy.data.objects[volume_name]
        bpy.data.objects.remove(old_volume, do_unlink=True)
    
    settings = context.scene.jopex_settings
    
    # Get target object bounds or use default size
    if settings.product_object:
        center = get_bbox_center(settings.product_object)
        size = get_object_size(settings.product_object) * 2
    else:
        center = Vector((0, 0, 0))
        size = 5.0
    
    # Apply volume scale
    size = size * settings.volume_scale
    
    # Create cube mesh using bmesh
    mesh = bpy.data.meshes.new(volume_name + "_mesh")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    bm.to_mesh(mesh)
    bm.free()
    
    # Create object and link to scene collection (safe in all contexts)
    volume_obj = bpy.data.objects.new(volume_name, mesh)
    volume_obj.location = center
    # Always display as wireframe in viewport
    volume_obj.display_type = 'WIRE'
    volume_obj.show_wire = True
    volume_obj.show_all_edges = True
    volume_obj.show_in_front = False
    context.scene.collection.objects.link(volume_obj)
    
    # Create volume material
    mat = bpy.data.materials.new(volume_name + "_mat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    
    nodes.clear()
    
    # Volume Scatter node
    volume_scatter = nodes.new(type='ShaderNodeVolumeScatter')
    volume_scatter.location = (0, 0)
    volume_scatter.inputs['Color'].default_value = (*settings.volume_color, 1.0)
    volume_scatter.inputs['Density'].default_value = settings.volume_density
    volume_scatter.inputs['Anisotropy'].default_value = settings.volume_anisotropy
    
    # Output node
    output = nodes.new(type='ShaderNodeOutputMaterial')
    output.location = (200, 0)
    
    # Connect
    links.new(volume_scatter.outputs['Volume'], output.inputs['Volume'])
    
    volume_obj.data.materials.append(mat)
    
    return volume_obj

def update_volume(context):
    """Update volume object settings"""
    settings = context.scene.jopex_settings
    volume_name = "Jopex_Volume"
    
    if settings.volume_enabled:
        if volume_name not in bpy.data.objects:
            create_volume_object(context)
        else:
            volume_obj = bpy.data.objects[volume_name]
            # Recreate to apply new scale cleanly (avoids edit-mode issues)
            create_volume_object(context)
    else:
        if volume_name in bpy.data.objects:
            volume_obj = bpy.data.objects[volume_name]
            bpy.data.objects.remove(volume_obj, do_unlink=True)

def update_ambience_light(context):
    try:
        settings = context.scene.jopex_settings
        
        if not bpy.data.worlds.get("Jopex_World"):
            world = bpy.data.worlds.new("Jopex_World")
            context.scene.world = world
        else:
            world = bpy.data.worlds["Jopex_World"]
            if context.scene.world != world:
                context.scene.world = world
        
        world.use_nodes = True
        nodes = world.node_tree.nodes
        links = world.node_tree.links
        
        nodes.clear()
        
        bg_node = nodes.new(type='ShaderNodeBackground')
        bg_node.location = (0, 0)
        
        output_node = nodes.new(type='ShaderNodeOutputWorld')
        output_node.location = (200, 0)
        
        links.new(bg_node.outputs[0], output_node.inputs[0])
        
        if settings.ambience_enabled:
            bg_node.inputs[0].default_value = (*settings.ambience_color, 1.0)
            bg_node.inputs[1].default_value = settings.ambience_strength
        else:
            bg_node.inputs[0].default_value = (0.0, 0.0, 0.0, 1.0)
            bg_node.inputs[1].default_value = 0.0
    except Exception as e:
        print("Jopex Light Studio - Ambience error:", e)

def _apply_viewport_hdri_visibility(settings):
    """Apply HDRI background visibility in all 3D viewports."""
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            # Show scene world so HDRI appears in viewport
                            if settings.hdri_enabled and settings.hdri_path:
                                space.shading.use_scene_world = True
                                space.shading.use_scene_world_render = True
    except Exception as e:
        print("Jopex viewport shading error:", e)


def update_hdri(context):
    try:
        settings = context.scene.jopex_settings
        
        if settings.ambience_enabled and not settings.hdri_enabled:
            update_ambience_light(context)
            return
            
        if not bpy.data.worlds.get("Jopex_World"):
            world = bpy.data.worlds.new("Jopex_World")
            context.scene.world = world
        else:
            world = bpy.data.worlds["Jopex_World"]
            if context.scene.world != world:
                context.scene.world = world
        
        world.use_nodes = True
        nodes = world.node_tree.nodes
        links = world.node_tree.links
        
        # Clear existing nodes
        nodes.clear()
        
        # 1. Texture Coordinate — use Object output for stable world-space HDRI
        tex_coord = nodes.new(type='ShaderNodeTexCoord')
        tex_coord.location = (-800, 0)
        
        # 2. Mapping for rotation
        mapping = nodes.new(type='ShaderNodeMapping')
        mapping.location = (-600, 0)
        links.new(tex_coord.outputs['Generated'], mapping.inputs['Vector'])
        
        # 3. Environment Texture
        env_tex = nodes.new(type='ShaderNodeTexEnvironment')
        env_tex.location = (-400, 0)
        links.new(mapping.outputs['Vector'], env_tex.inputs['Vector'])
        
        if settings.hdri_path and settings.hdri_enabled:
            try:
                img = bpy.data.images.load(settings.hdri_path, check_existing=True)
                # Mark as HDRI so Blender handles it correctly
                img.colorspace_settings.name = 'Linear' if img.colorspace_settings.name not in ('Linear', 'Linear Rec.709') else img.colorspace_settings.name
                env_tex.image = img
            except Exception as e:
                print("HDRI load error:", e)
        
        # 4. Background with strength
        bg = nodes.new(type='ShaderNodeBackground')
        bg.location = (-200, 0)
        bg.inputs['Strength'].default_value = settings.hdri_strength
        links.new(env_tex.outputs['Color'], bg.inputs['Color'])
        
        # 5. World Output
        output = nodes.new(type='ShaderNodeOutputWorld')
        output.location = (200, 0)
        
        # 6. Show Background toggle — use film transparency for render,
        #    and shader Mix for both viewport and render
        if settings.hdri_background_visible:
            # Show background: wire straight to output
            links.new(bg.outputs['Background'], output.inputs['Surface'])
            context.scene.render.film_transparent = False
        else:
            # Hide background: transparent surface, keep lighting
            transparent = nodes.new(type='ShaderNodeBackground')
            transparent.location = (-200, -150)
            transparent.inputs['Color'].default_value = (0, 0, 0, 1)
            transparent.inputs['Strength'].default_value = 0.0
            links.new(transparent.outputs['Background'], output.inputs['Surface'])
            context.scene.render.film_transparent = True
        
        # Apply rotation
        mapping.inputs['Rotation'].default_value[2] = math.radians(settings.hdri_rotation)
        
        # If HDRI is disabled or no path, set strength to 0
        if not settings.hdri_enabled or not settings.hdri_path:
            if settings.ambience_enabled:
                update_ambience_light(context)
            else:
                bg.inputs['Strength'].default_value = 0
        
        # Make HDRI visible in viewport shading
        _apply_viewport_hdri_visibility(settings)
                
    except Exception as e:
        print("Jopex Light Studio - HDRI error:", e)
def update_single_light(context, light_name, property_type):
    try:
        settings = context.scene.jopex_settings
        light_obj = bpy.data.objects.get(light_name)
        
        if not light_obj or not light_obj.data:
            return
        
        light_settings = None
        for ls in settings.lights:
            if ls.name == light_name:
                light_settings = ls
                break
        
        if not light_settings:
            return
        
        if property_type == 'power':
            light_obj.data.energy = light_settings.power * settings.master_power
        
        elif property_type == 'color':
            light_obj.data.color = light_settings.color
        
        elif property_type == 'light_type':
            old_energy = light_obj.data.energy
            old_color = light_obj.data.color
            light_obj.data.type = light_settings.light_type
            light_obj.data.energy = old_energy
            light_obj.data.color = old_color
        
        elif property_type == 'size':
            final_size = light_settings.size * settings.master_scale
            if light_obj.data.type == 'AREA':
                light_obj.data.size = final_size
            elif light_obj.data.type == 'SPOT':
                light_obj.data.spot_size = final_size
            elif light_obj.data.type == 'POINT':
                light_obj.data.shadow_soft_size = final_size
            elif light_obj.data.type == 'SUN':
                light_obj.data.angle = final_size
        
        elif property_type == 'enabled':
            light_obj.hide_viewport = not light_settings.enabled
            light_obj.hide_render = not light_settings.enabled
        
        elif property_type == 'shadow':
            light_obj.data.use_shadow = light_settings.use_shadow
        
        elif property_type == 'shadow_softness':
            if hasattr(light_obj.data, 'shadow_soft_size'):
                light_obj.data.shadow_soft_size = light_settings.shadow_softness
            elif hasattr(light_obj.data, 'angle'):
                light_obj.data.angle = light_settings.shadow_softness
        
        elif property_type == 'position':
            if settings.product_object:
                center = get_bbox_center(settings.product_object)
                dist = light_settings.distance * settings.master_distance * settings.master_scale
                angle = light_settings.angle + settings.master_angle_offset
                height = (light_settings.height + settings.master_height_offset) * settings.master_scale
                
                angle_rad = math.radians(angle)
                x = center.x + dist * math.cos(angle_rad)
                y = center.y + dist * math.sin(angle_rad)
                z = center.z + height
                light_obj.location = Vector((x, y, z))
                
                rig_name = "Jopex_Lighting_Rig"
                rig = bpy.data.objects.get(rig_name)
                
                if rig and light_settings.use_rig_control:
                    # Ensure exactly one clean TRACK_TO constraint
                    for c in list(light_obj.constraints):
                        light_obj.constraints.remove(c)
                    con = light_obj.constraints.new(type='TRACK_TO')
                    con.target = rig
                    con.track_axis = 'TRACK_NEGATIVE_Z'
                    con.up_axis = 'UP_Y'
                else:
                    # Remove constraints, point manually at rig/center
                    for c in list(light_obj.constraints):
                        light_obj.constraints.remove(c)
                    rig = bpy.data.objects.get(rig_name)
                    if rig:
                        point_light_at_target(light_obj, rig)
                    else:
                        # point toward product center
                        dummy_center = get_bbox_center(settings.product_object) if settings.product_object else Vector((0,0,0))
                        direction = dummy_center - light_obj.location
                        if direction.length > 0.0001:
                            rot_quat = direction.normalized().to_track_quat('-Z', 'Y')
                            light_obj.rotation_euler = rot_quat.to_euler()
        
        refresh_ui()
    except Exception as e:
        print("Jopex Light Studio - Update light error:", e)

def point_light_at_target(light_obj, target_obj):
    """Directly rotate a light object to face the target using pure math.
    This avoids any local-axis skew caused by constraints like DAMPED_TRACK.
    Area lights emit along their local -Z axis, so we align -Z toward the target."""
    if not target_obj:
        return
    
    direction = target_obj.location - light_obj.location
    if direction.length < 0.0001:
        return
    
    # Area / Spot lights emit along local -Z. Rotate so -Z points at target.
    rot_quat = direction.normalized().to_track_quat('-Z', 'Y')
    light_obj.rotation_euler = rot_quat.to_euler()


def create_single_light(context, name, light_role, light_data_type, angle, distance, height, color, power, size, use_rig_control=True):
    try:
        settings = context.scene.jopex_settings
        
        if not settings.product_object:
            return None
        
        center = get_bbox_center(settings.product_object)
        
        light_data = bpy.data.lights.new(name=name, type=light_data_type)
        light_data.energy = power
        light_data.color = color
        
        scaled_size = size * settings.master_scale
        
        if light_data_type == 'AREA':
            light_data.size = scaled_size
        elif light_data_type == 'SPOT':
            light_data.spot_size = scaled_size
            light_data.spot_blend = 0.15
        elif light_data_type == 'POINT':
            light_data.shadow_soft_size = scaled_size
        elif light_data_type == 'SUN':
            light_data.angle = scaled_size
        
        light_data.use_shadow = True
        
        light_obj = bpy.data.objects.new(name=name, object_data=light_data)
        light_obj["jopex_light"] = True
        # Always link to scene collection for reliable placement
        context.scene.collection.objects.link(light_obj)
        
        scaled_distance = distance * settings.master_scale
        scaled_height = height * settings.master_scale
        
        angle_rad = math.radians(angle)
        x = center.x + scaled_distance * math.cos(angle_rad)
        y = center.y + scaled_distance * math.sin(angle_rad)
        z = center.z + scaled_height
        
        light_obj.location = Vector((x, y, z))
        light_obj.show_name = True
        
        rig_name = "Jopex_Lighting_Rig"
        rig = bpy.data.objects.get(rig_name)
        
        if rig and use_rig_control:
            # Remove any stale constraints
            for c in list(light_obj.constraints):
                light_obj.constraints.remove(c)
            # TRACK_TO with -Z forward cleanly points the light.
            # 'UP_Y' keeps the vertical axis stable so area lights stay square.
            con = light_obj.constraints.new(type='TRACK_TO')
            con.target = rig
            con.track_axis = 'TRACK_NEGATIVE_Z'
            con.up_axis = 'UP_Y'
        else:
            # No rig: point directly at the center of the product using math
            rig_target = bpy.data.objects.get(rig_name)
            if rig_target:
                point_light_at_target(light_obj, rig_target)
            else:
                # Point at product center
                dummy = type('obj', (object,), {'location': center})()
                point_light_at_target(light_obj, dummy)
        
        light_setting = settings.lights.add()
        light_setting.name = name
        light_setting.light_type = light_data_type
        light_setting.power = power
        light_setting.color = color
        light_setting.distance = distance
        light_setting.angle = angle
        light_setting.height = height
        light_setting.size = size
        light_setting.light_role = light_role
        light_setting.use_rig_control = use_rig_control
        
        refresh_ui()
        return light_obj
    except Exception as e:
        print("Jopex Light Studio - Create light error:", e)
        return None

# ==============================================
# QUICK PRESETS - No extra rotation, just angle around Z
# ==============================================

def apply_quick_preset_3point(context, center, object_size):
    base_dist = max(2.5, object_size * 2.2)
    
    create_single_light(context, "Key Light", "KEY", 'AREA',
        45, base_dist * 0.9, center.z + object_size * 0.8,
        (1.0, 0.95, 0.9), 180.0, 0.5)
    
    create_single_light(context, "Fill Light", "FILL", 'AREA',
        315, base_dist * 0.8, center.z + object_size * 0.5,
        (0.9, 0.95, 1.0), 70.0, 0.8)
    
    create_single_light(context, "Rim Light", "RIM", 'AREA',
        180, base_dist * 1.1, center.z + object_size * 1.3,
        (1.0, 0.98, 0.95), 120.0, 0.3)

def apply_quick_preset_product(context, center, object_size):
    base_dist = max(2.5, object_size * 2.0)
    
    create_single_light(context, "Soft Key", "KEY", 'AREA',
        0, base_dist * 0.6, center.z + object_size * 1.3,
        (1.0, 1.0, 1.0), 200.0, 1.2)
    
    create_single_light(context, "Fill L", "FILL", 'AREA',
        90, base_dist * 0.7, center.z + object_size * 0.6,
        (1.0, 1.0, 1.0), 100.0, 0.8)
    
    create_single_light(context, "Fill R", "FILL", 'AREA',
        270, base_dist * 0.7, center.z + object_size * 0.6,
        (1.0, 1.0, 1.0), 100.0, 0.8)
    
    create_single_light(context, "Top Fill", "TOP", 'AREA',
        0, base_dist * 0.2, center.z + object_size * 1.8,
        (1.0, 1.0, 1.0), 80.0, 1.0)

def apply_quick_preset_portrait(context, center, object_size):
    base_dist = max(2.5, object_size * 2.0)
    
    create_single_light(context, "Key Light", "KEY", 'AREA',
        45, base_dist * 0.8, center.z + object_size * 1.0,
        (1.0, 0.92, 0.85), 160.0, 0.6)
    
    create_single_light(context, "Fill Light", "FILL", 'AREA',
        315, base_dist * 0.9, center.z + object_size * 0.4,
        (0.85, 0.88, 1.0), 50.0, 0.7)
    
    create_single_light(context, "Hair Light", "RIM", 'AREA',
        200, base_dist * 0.7, center.z + object_size * 1.6,
        (1.0, 0.96, 0.9), 100.0, 0.3)

def apply_quick_preset_cinematic(context, center, object_size):
    base_dist = max(2.5, object_size * 2.5)
    
    create_single_light(context, "Hard Key", "KEY", 'AREA',
        75, base_dist * 0.7, center.z + object_size * 0.7,
        (1.0, 0.85, 0.7), 220.0, 0.15)
    
    create_single_light(context, "Moody Fill", "FILL", 'AREA',
        300, base_dist * 1.0, center.z + object_size * 0.3,
        (0.5, 0.6, 1.0), 30.0, 1.0)
    
    create_single_light(context, "Cine Rim", "RIM", 'AREA',
        200, base_dist * 0.8, center.z + object_size * 1.4,
        (1.0, 0.7, 0.5), 150.0, 0.1)

def apply_quick_preset_dramatic(context, center, object_size):
    base_dist = max(2.5, object_size * 2.5)
    
    create_single_light(context, "Dramatic Key", "KEY", 'SPOT',
        95, base_dist * 0.6, center.z + object_size * 0.5,
        (1.0, 0.9, 0.8), 300.0, 0.08)
    
    create_single_light(context, "Under Fill", "FILL", 'POINT',
        0, base_dist * 0.4, center.z - object_size * 1.0,
        (0.5, 0.6, 1.0), 25.0, 0.3)
    
    create_single_light(context, "Drama Rim", "RIM", 'SPOT',
        185, base_dist * 0.9, center.z + object_size * 1.2,
        (1.0, 0.85, 0.7), 120.0, 0.08)
    
    create_single_light(context, "Side Accent", "SIDE", 'AREA',
        135, base_dist * 0.8, center.z + object_size * 0.3,
        (0.9, 0.8, 1.0), 40.0, 0.15)

def apply_quick_preset_outdoor(context, center, object_size):
    base_dist = max(4.0, object_size * 2.8)
    
    create_single_light(context, "Sun Light", "SUN", 'SUN',
        35, base_dist, center.z + object_size * 5.0,
        (1.0, 0.96, 0.88), 5.0, 0.03)
    
    create_single_light(context, "Sky Fill", "FILL", 'AREA',
        135, base_dist * 0.8, center.z + object_size * 2.0,
        (0.7, 0.85, 1.0), 1.5, 2.5)
    
    create_single_light(context, "Ground Bounce", "FILL", 'AREA',
        0, base_dist * 0.5, center.z - object_size * 0.5,
        (0.95, 0.85, 0.7), 30.0, 1.0)

# ==============================================
# PROPERTY GROUPS
# ==============================================

class JopexLightSettings(PropertyGroup):
    name: StringProperty(name="Light Name", default="")
    light_type: EnumProperty(
        name="Light Type",
        items=[
            ('AREA', "Area", "Area light", 'LIGHT_AREA', 1),
            ('POINT', "Point", "Point light", 'LIGHT_POINT', 2),
            ('SUN', "Sun", "Sun light", 'LIGHT_SUN', 3),
            ('SPOT', "Spot", "Spot light", 'LIGHT_SPOT', 4),
        ],
        default='AREA',
        update=lambda self, context: update_single_light(context, self.name, 'light_type')
    )
    
    light_role: StringProperty(default="")
    
    enabled: BoolProperty(
        name="Enabled", default=True,
        update=lambda self, context: update_single_light(context, self.name, 'enabled')
    )
    
    use_rig_control: BoolProperty(
        name="Use Rig Control", default=True,
        update=lambda self, context: update_single_light(context, self.name, 'position')
    )
    
    power: FloatProperty(
        name="Power", default=100.0, min=1.0, max=1000.0,
        update=lambda self, context: update_single_light(context, self.name, 'power')
    )
    
    color: FloatVectorProperty(
        name="Color", subtype='COLOR', size=3, default=(1.0, 1.0, 1.0), min=0.0, max=1.0,
        update=lambda self, context: update_single_light(context, self.name, 'color')
    )
    
    distance: FloatProperty(
        name="Distance", default=3.0, min=0.1, max=500.0,
        update=lambda self, context: update_single_light(context, self.name, 'position')
    )
    
    angle: FloatProperty(
        name="Angle", default=0.0, min=-360.0, max=360.0,
        update=lambda self, context: update_single_light(context, self.name, 'position')
    )
    
    show_details: BoolProperty(name="Show Details", default=False)
    
    height: FloatProperty(
        name="Height", default=2.0, min=-500.0, max=500.0,
        update=lambda self, context: update_single_light(context, self.name, 'position')
    )
    
    size: FloatProperty(
        name="Size", default=0.5, min=0.01, max=500.0,
        update=lambda self, context: update_single_light(context, self.name, 'size')
    )
    
    use_shadow: BoolProperty(
        name="Shadows", default=True,
        update=lambda self, context: update_single_light(context, self.name, 'shadow')
    )
    
    shadow_softness: FloatProperty(
        name="Softness", default=0.3, min=0.0, max=2.0,
        update=lambda self, context: update_single_light(context, self.name, 'shadow_softness')
    )

class JopexStudioSettings(PropertyGroup):
    product_object: PointerProperty(name="Target Object", type=bpy.types.Object)
    
    # Master Controls
    master_power: FloatProperty(
        name="All Power", default=1.0, min=0.0, max=2.0,
        update=lambda self, context: bpy.ops.jopex.update_master_power()
    )
    
    master_distance: FloatProperty(
        name="All Distance", default=1.0, min=0.5, max=3.0,
        update=lambda self, context: bpy.ops.jopex.apply_global_settings()
    )
    
    master_angle_offset: FloatProperty(
        name="All Angle Offset", default=0.0, min=-180.0, max=180.0,
        update=lambda self, context: bpy.ops.jopex.apply_global_settings()
    )
    
    master_height_offset: FloatProperty(
        name="All Height", default=0.0, min=-50.0, max=50.0,
        update=lambda self, context: bpy.ops.jopex.apply_global_settings()
    )
    
    master_scale: FloatProperty(
        name="Master Scale", default=1.0, min=0.01, max=1000.0,
        update=lambda self, context: bpy.ops.jopex.apply_master_scale()
    )
    
    master_color: FloatVectorProperty(
        name="All Color", subtype='COLOR', size=3, default=(1.0, 1.0, 1.0), min=0.0, max=1.0,
        update=lambda self, context: bpy.ops.jopex.apply_global_color()
    )
    
    master_light_type: EnumProperty(
        name="All Type",
        items=[
            ('AREA', "Area", "Area light", 'LIGHT_AREA', 1),
            ('POINT', "Point", "Point light", 'LIGHT_POINT', 2),
            ('SUN', "Sun", "Sun light", 'LIGHT_SUN', 3),
            ('SPOT', "Spot", "Spot light", 'LIGHT_SPOT', 4),
        ],
        default='AREA',
        update=lambda self, context: bpy.ops.jopex.apply_global_type()
    )
    
    # Ambience Settings
    ambience_enabled: BoolProperty(
        name="Enable Ambience", default=False,
        update=lambda self, context: update_ambience_light(context)
    )
    
    ambience_strength: FloatProperty(
        name="Ambience Strength", default=0.5, min=0.0, max=10.0,
        update=lambda self, context: update_ambience_light(context)
    )
    
    ambience_color: FloatVectorProperty(
        name="Ambience Color", subtype='COLOR', size=3, default=(0.5, 0.5, 0.5), min=0.0, max=1.0,
        update=lambda self, context: update_ambience_light(context)
    )
    
    # HDRI Settings
    hdri_enabled: BoolProperty(
        name="Enable HDRI", default=False,
        update=lambda self, context: update_hdri(context)
    )
    hdri_path: StringProperty(
        name="HDRI Path", default="", subtype='FILE_PATH',
        update=lambda self, context: update_hdri(context)
    )
    hdri_strength: FloatProperty(
        name="Strength", default=1.0, min=0.0, max=50.0,
        update=lambda self, context: update_hdri(context)
    )
    hdri_rotation: FloatProperty(
        name="Rotation", default=0.0, min=0.0, max=360.0,
        update=lambda self, context: update_hdri(context)
    )
    hdri_background_visible: BoolProperty(
        name="Show Background", default=True,
        description="Toggle HDRI background visibility (render & viewport)",
        update=lambda self, context: update_hdri(context)
    )
    
    # Volume Settings
    volume_enabled: BoolProperty(
        name="Enable Volume", default=False,
        update=lambda self, context: update_volume(context)
    )
    volume_density: FloatProperty(
        name="Density", default=0.1, min=0.0, max=1.0,
        update=lambda self, context: update_volume(context)
    )
    volume_anisotropy: FloatProperty(
        name="Anisotropy", default=0.0, min=-1.0, max=1.0,
        update=lambda self, context: update_volume(context)
    )
    volume_color: FloatVectorProperty(
        name="Color", subtype='COLOR', size=3, default=(1.0, 1.0, 1.0), min=0.0, max=1.0,
        update=lambda self, context: update_volume(context)
    )
    volume_scale: FloatProperty(
        name="Volume Scale", default=1.0, min=0.1, max=10.0,
        update=lambda self, context: update_volume(context)
    )
    
    lights: CollectionProperty(type=JopexLightSettings)
    active_light_index: IntProperty(default=0)

# ==============================================
# MENUS
# ==============================================

class JOPEX_MT_quick_presets(Menu):
    bl_label = "Quick Presets"
    bl_idname = "JOPEX_MT_quick_presets"
    
    def draw(self, context):
        layout = self.layout
        layout.operator("jopex.quick_preset_3point", text="3 Point Studio", icon='LIGHT_AREA')
        layout.operator("jopex.quick_preset_product", text="Product Soft", icon='LIGHT_AREA')
        layout.operator("jopex.quick_preset_portrait", text="Portrait", icon='USER')
        layout.operator("jopex.quick_preset_cinematic", text="Cinematic", icon='CAMERA_STEREO')
        layout.operator("jopex.quick_preset_dramatic", text="Dramatic", icon='LIGHT')
        layout.operator("jopex.quick_preset_outdoor", text="Outdoor Sun", icon='LIGHT_SUN')

class JOPEX_MT_load_preset(Menu):
    bl_label = "Load Preset"
    bl_idname = "JOPEX_MT_load_preset"
    
    def draw(self, context):
        layout = self.layout
        addon_dir = os.path.dirname(os.path.abspath(__file__))
        presets_dir = os.path.join(addon_dir, "presets")
        
        if os.path.exists(presets_dir):
            preset_files = [f for f in os.listdir(presets_dir) if f.endswith('.json')]
            if preset_files:
                for preset_file in preset_files:
                    op = layout.operator("jopex.load_preset", text=preset_file.replace('.json', ''))
                    op.preset_file = os.path.join(presets_dir, preset_file)
            else:
                layout.label(text="No saved presets found")
        else:
            layout.label(text="No presets directory found")

# ==============================================
# OPERATORS
# ==============================================

class JOPEX_OT_quick_preset_3point(Operator):
    bl_idname = "jopex.quick_preset_3point"
    bl_label = "3 Point Studio"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        settings = context.scene.jopex_settings
        if not settings.product_object:
            self.report({'ERROR'}, "Please select a target object first!")
            return {'CANCELLED'}
        
        clear_jopex_lights()
        settings.lights.clear()
        create_lighting_rig(context)
        
        center = get_bbox_center(settings.product_object)
        object_size = get_object_size(settings.product_object)
        apply_quick_preset_3point(context, center, object_size)
        
        refresh_ui()
        self.report({'INFO'}, "Applied 3 Point Studio preset with rig")
        return {'FINISHED'}

class JOPEX_OT_quick_preset_product(Operator):
    bl_idname = "jopex.quick_preset_product"
    bl_label = "Product Soft"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        settings = context.scene.jopex_settings
        if not settings.product_object:
            self.report({'ERROR'}, "Please select a target object first!")
            return {'CANCELLED'}
        
        clear_jopex_lights()
        settings.lights.clear()
        create_lighting_rig(context)
        
        center = get_bbox_center(settings.product_object)
        object_size = get_object_size(settings.product_object)
        apply_quick_preset_product(context, center, object_size)
        
        refresh_ui()
        self.report({'INFO'}, "Applied Product Soft preset with rig")
        return {'FINISHED'}

class JOPEX_OT_quick_preset_portrait(Operator):
    bl_idname = "jopex.quick_preset_portrait"
    bl_label = "Portrait"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        settings = context.scene.jopex_settings
        if not settings.product_object:
            self.report({'ERROR'}, "Please select a target object first!")
            return {'CANCELLED'}
        
        clear_jopex_lights()
        settings.lights.clear()
        create_lighting_rig(context)
        
        center = get_bbox_center(settings.product_object)
        object_size = get_object_size(settings.product_object)
        apply_quick_preset_portrait(context, center, object_size)
        
        refresh_ui()
        self.report({'INFO'}, "Applied Portrait preset with rig")
        return {'FINISHED'}

class JOPEX_OT_quick_preset_cinematic(Operator):
    bl_idname = "jopex.quick_preset_cinematic"
    bl_label = "Cinematic"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        settings = context.scene.jopex_settings
        if not settings.product_object:
            self.report({'ERROR'}, "Please select a target object first!")
            return {'CANCELLED'}
        
        clear_jopex_lights()
        settings.lights.clear()
        create_lighting_rig(context)
        
        center = get_bbox_center(settings.product_object)
        object_size = get_object_size(settings.product_object)
        apply_quick_preset_cinematic(context, center, object_size)
        
        refresh_ui()
        self.report({'INFO'}, "Applied Cinematic preset with rig")
        return {'FINISHED'}

class JOPEX_OT_quick_preset_dramatic(Operator):
    bl_idname = "jopex.quick_preset_dramatic"
    bl_label = "Dramatic"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        settings = context.scene.jopex_settings
        if not settings.product_object:
            self.report({'ERROR'}, "Please select a target object first!")
            return {'CANCELLED'}
        
        clear_jopex_lights()
        settings.lights.clear()
        create_lighting_rig(context)
        
        center = get_bbox_center(settings.product_object)
        object_size = get_object_size(settings.product_object)
        apply_quick_preset_dramatic(context, center, object_size)
        
        refresh_ui()
        self.report({'INFO'}, "Applied Dramatic preset with rig")
        return {'FINISHED'}

class JOPEX_OT_quick_preset_outdoor(Operator):
    bl_idname = "jopex.quick_preset_outdoor"
    bl_label = "Outdoor Sun"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        settings = context.scene.jopex_settings
        if not settings.product_object:
            self.report({'ERROR'}, "Please select a target object first!")
            return {'CANCELLED'}
        
        clear_jopex_lights()
        settings.lights.clear()
        create_lighting_rig(context)
        
        center = get_bbox_center(settings.product_object)
        object_size = get_object_size(settings.product_object)
        apply_quick_preset_outdoor(context, center, object_size)
        
        refresh_ui()
        self.report({'INFO'}, "Applied Outdoor Sun preset with rig")
        return {'FINISHED'}

class JOPEX_OT_add_light(Operator):
    bl_idname = "jopex.add_light"
    bl_label = "Add New Light"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        settings = context.scene.jopex_settings
        if not settings.product_object:
            self.report({'ERROR'}, "Please select a target object first!")
            return {'CANCELLED'}
        
        center = get_bbox_center(settings.product_object)
        light_count = len(settings.lights) + 1
        name = f"Jopex_Light_{light_count}"
        
        create_single_light(context, name, "CUSTOM", 'AREA',
            0, 3.0, center.z + 1.5, (1.0, 1.0, 1.0), 100.0, 0.5, True)
        
        refresh_ui()
        self.report({'INFO'}, f"Added {name}")
        return {'FINISHED'}

class JOPEX_OT_load_hdri(Operator):
    bl_idname = "jopex.load_hdri"
    bl_label = "Load HDRI"
    bl_options = {'REGISTER', 'UNDO'}
    
    filepath: StringProperty(subtype='FILE_PATH')
    
    def execute(self, context):
        settings = context.scene.jopex_settings
        settings.hdri_path = self.filepath
        settings.hdri_enabled = True
        settings.ambience_enabled = False
        update_hdri(context)
        self.report({'INFO'}, f"Loaded HDRI: {os.path.basename(self.filepath)}")
        return {'FINISHED'}
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class JOPEX_OT_toggle_rig_control(Operator):
    bl_idname = "jopex.toggle_rig_control"
    bl_label = "Toggle Rig Control"
    light_index: IntProperty()
    
    def execute(self, context):
        settings = context.scene.jopex_settings
        if self.light_index < len(settings.lights):
            light_settings = settings.lights[self.light_index]
            light_settings.use_rig_control = not light_settings.use_rig_control
            update_single_light(context, light_settings.name, 'position')
        return {'FINISHED'}

class JOPEX_OT_toggle_light(Operator):
    bl_idname = "jopex.toggle_light"
    bl_label = "Toggle Light"
    light_index: IntProperty()
    
    def execute(self, context):
        settings = context.scene.jopex_settings
        if self.light_index < len(settings.lights):
            light_settings = settings.lights[self.light_index]
            light_settings.enabled = not light_settings.enabled
            update_single_light(context, light_settings.name, 'enabled')
        return {'FINISHED'}

class JOPEX_OT_toggle_details(Operator):
    bl_idname = "jopex.toggle_details"
    bl_label = "Toggle Details"
    light_index: IntProperty()
    
    def execute(self, context):
        settings = context.scene.jopex_settings
        if self.light_index < len(settings.lights):
            settings.lights[self.light_index].show_details = not settings.lights[self.light_index].show_details
            refresh_ui()
        return {'FINISHED'}

class JOPEX_OT_select_object(Operator):
    bl_idname = "jopex.select_object"
    bl_label = "Register Selected Object"
    
    def execute(self, context):
        if context.active_object and context.active_object.type != 'LIGHT' and context.active_object.name != "Jopex_Lighting_Rig":
            context.scene.jopex_settings.product_object = context.active_object
            refresh_ui()
            self.report({'INFO'}, f"Registered: {context.active_object.name}")
        else:
            self.report({'ERROR'}, "Please select a valid 3D object in the viewport first.")
        return {'FINISHED'}

class JOPEX_OT_remove_light(Operator):
    bl_idname = "jopex.remove_light"
    bl_label = "Remove Light"
    light_index: IntProperty()
    
    def execute(self, context):
        settings = context.scene.jopex_settings
        if self.light_index < len(settings.lights):
            light = settings.lights[self.light_index]
            obj = bpy.data.objects.get(light.name)
            if obj:
                bpy.data.objects.remove(obj, do_unlink=True)
            settings.lights.remove(self.light_index)
            refresh_ui()
            self.report({'INFO'}, f"Removed {light.name}")
        return {'FINISHED'}

class JOPEX_OT_clear_all_lights(Operator):
    bl_idname = "jopex.clear_all_lights"
    bl_label = "Clear All Jopex Lights"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        clear_jopex_lights()
        context.scene.jopex_settings.lights.clear()
        refresh_ui()
        self.report({'INFO'}, "Cleared all Jopex lights, rig, and volume")
        return {'FINISHED'}

class JOPEX_OT_reset_preset(Operator):
    bl_idname = "jopex.reset_preset"
    bl_label = "Reset Preset"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        settings = context.scene.jopex_settings
        if not settings.product_object:
            self.report({'ERROR'}, "Please select a target object first!")
            return {'CANCELLED'}
        
        clear_jopex_lights()
        settings.lights.clear()
        create_lighting_rig(context)
        
        center = get_bbox_center(settings.product_object)
        object_size = get_object_size(settings.product_object)
        apply_quick_preset_3point(context, center, object_size)
        
        refresh_ui()
        self.report({'INFO'}, "Reset to 3 Point Studio")
        return {'FINISHED'}

class JOPEX_OT_save_preset(Operator):
    bl_idname = "jopex.save_preset"
    bl_label = "Save Preset"
    bl_options = {'REGISTER', 'UNDO'}
    
    preset_name: StringProperty(name="Preset Name", default="MyPreset")
    
    def execute(self, context):
        settings = context.scene.jopex_settings
        if not settings.lights:
            self.report({'WARNING'}, "No lights to save!")
            return {'CANCELLED'}
        
        addon_dir = os.path.dirname(os.path.abspath(__file__))
        presets_dir = os.path.join(addon_dir, "presets")
        if not os.path.exists(presets_dir):
            os.makedirs(presets_dir)
        
        preset_data = {
            "name": self.preset_name, 
            "lights": [],
            "ambience": {
                "enabled": settings.ambience_enabled,
                "strength": settings.ambience_strength,
                "color": list(settings.ambience_color),
            },
            "hdri": {
                "enabled": settings.hdri_enabled,
                "path": settings.hdri_path,
                "strength": settings.hdri_strength,
                "rotation": settings.hdri_rotation,
                "background_visible": settings.hdri_background_visible,
            },
            "volume": {
                "enabled": settings.volume_enabled,
                "density": settings.volume_density,
                "anisotropy": settings.volume_anisotropy,
                "color": list(settings.volume_color),
                "scale": settings.volume_scale,
            }
        }
        
        for light in settings.lights:
            light_data = {
                "name": light.name, "light_type": light.light_type, "light_role": light.light_role,
                "power": light.power, "color": list(light.color), "distance": light.distance,
                "angle": light.angle, "height": light.height, "size": light.size,
                "use_rig_control": light.use_rig_control, "use_shadow": light.use_shadow,
                "shadow_softness": light.shadow_softness
            }
            preset_data["lights"].append(light_data)
        
        file_path = os.path.join(presets_dir, f"{self.preset_name}.json")
        with open(file_path, 'w') as f:
            json.dump(preset_data, f, indent=4)
        
        self.report({'INFO'}, f"Preset '{self.preset_name}' saved")
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

class JOPEX_OT_load_preset(Operator):
    bl_idname = "jopex.load_preset"
    bl_label = "Load Preset"
    bl_options = {'REGISTER', 'UNDO'}
    preset_file: StringProperty()
    
    def execute(self, context):
        settings = context.scene.jopex_settings
        if not settings.product_object:
            self.report({'ERROR'}, "Please select a target object first!")
            return {'CANCELLED'}
        
        try:
            with open(self.preset_file, 'r') as f:
                preset_data = json.load(f)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to load preset: {e}")
            return {'CANCELLED'}
        
        clear_jopex_lights()
        settings.lights.clear()
        create_lighting_rig(context)
        
        # Load Ambience settings
        if "ambience" in preset_data:
            amb = preset_data["ambience"]
            settings.ambience_enabled = amb.get("enabled", False)
            settings.ambience_strength = amb.get("strength", 0.5)
            settings.ambience_color = amb.get("color", [0.5, 0.5, 0.5])
        
        # Load HDRI settings
        if "hdri" in preset_data:
            hdri = preset_data["hdri"]
            settings.hdri_enabled = hdri.get("enabled", False)
            settings.hdri_path = hdri.get("path", "")
            settings.hdri_strength = hdri.get("strength", 1.0)
            settings.hdri_rotation = hdri.get("rotation", 0.0)
            settings.hdri_background_visible = hdri.get("background_visible", True)
        
        # Load Volume settings
        if "volume" in preset_data:
            vol = preset_data["volume"]
            settings.volume_enabled = vol.get("enabled", False)
            settings.volume_density = vol.get("density", 0.1)
            settings.volume_anisotropy = vol.get("anisotropy", 0.0)
            settings.volume_color = vol.get("color", [1.0, 1.0, 1.0])
            settings.volume_scale = vol.get("scale", 1.0)
        
        # Update world
        if settings.hdri_enabled and settings.hdri_path:
            update_hdri(context)
        elif settings.ambience_enabled:
            update_ambience_light(context)
        
        # Update volume
        update_volume(context)
        
        # Load lights
        for light_data in preset_data["lights"]:
            color = tuple(light_data["color"])
            create_single_light(context, light_data["name"], light_data["light_role"],
                light_data["light_type"], light_data["angle"], light_data["distance"],
                light_data["height"], color, light_data["power"], light_data["size"],
                light_data["use_rig_control"])
            
            for light in settings.lights:
                if light.name == light_data["name"]:
                    light.use_shadow = light_data.get("use_shadow", True)
                    light.shadow_softness = light_data.get("shadow_softness", 0.3)
                    break
        
        refresh_ui()
        self.report({'INFO'}, f"Loaded preset: {preset_data.get('name', 'Unknown')}")
        return {'FINISHED'}

class JOPEX_OT_update_master_power(Operator):
    bl_idname = "jopex.update_master_power"
    bl_label = "Update Master Power"
    
    def execute(self, context):
        settings = context.scene.jopex_settings
        for light_settings in settings.lights:
            light_obj = bpy.data.objects.get(light_settings.name)
            if light_obj and light_obj.data:
                light_obj.data.energy = light_settings.power * settings.master_power
        return {'FINISHED'}

class JOPEX_OT_apply_global_settings(Operator):
    bl_idname = "jopex.apply_global_settings"
    bl_label = "Apply Global Settings"
    
    def execute(self, context):
        settings = context.scene.jopex_settings
        for light_settings in settings.lights:
            update_single_light(context, light_settings.name, 'position')
            update_single_light(context, light_settings.name, 'size')
        return {'FINISHED'}

class JOPEX_OT_apply_master_scale(Operator):
    bl_idname = "jopex.apply_master_scale"
    bl_label = "Apply Master Scale"
    
    def execute(self, context):
        settings = context.scene.jopex_settings
        rig = bpy.data.objects.get("Jopex_Lighting_Rig")
        if rig:
            rig.empty_display_size = 0.3 * settings.master_scale
        
        for light_settings in settings.lights:
            update_single_light(context, light_settings.name, 'position')
            update_single_light(context, light_settings.name, 'size')
        
        refresh_ui()
        return {'FINISHED'}

class JOPEX_OT_apply_global_type(Operator):
    bl_idname = "jopex.apply_global_type"
    bl_label = "Apply Global Type"
    
    def execute(self, context):
        settings = context.scene.jopex_settings
        for light_settings in settings.lights:
            light_settings.light_type = settings.master_light_type
        return {'FINISHED'}

class JOPEX_OT_apply_global_color(Operator):
    bl_idname = "jopex.apply_global_color"
    bl_label = "Apply Global Color"
    
    def execute(self, context):
        settings = context.scene.jopex_settings
        for light_settings in settings.lights:
            light_settings.color = settings.master_color
        return {'FINISHED'}

# ==============================================
# UI PANELS
# ==============================================

class JOPEX_PT_main(Panel):
    bl_label = "JOPEX LIGHT STUDIO"
    bl_idname = "JOPEX_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Jopex Light Studio"
    
    def draw_header(self, context):
        global custom_icons
        if custom_icons and "jopex_logo" in custom_icons:
            self.layout.label(text="", icon_value=custom_icons["jopex_logo"].icon_id)
        else:
            self.layout.label(text="", icon='LIGHT')
    
    def draw(self, context):
        layout = self.layout
        layout.separator()

class JOPEX_PT_quick_presets(Panel):
    bl_label = "QUICK PRESETS"
    bl_idname = "JOPEX_PT_quick_presets"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Jopex Light Studio"
    bl_parent_id = "JOPEX_PT_main"
    
    def draw(self, context):
        layout = self.layout
        settings = context.scene.jopex_settings
        
        target_box = layout.box()
        row = target_box.row(align=True)
        row.label(text="Target Object", icon='OBJECT_DATA')
        if not settings.product_object:
            row.label(text="REQUIRED", icon='ERROR')
        
        selector = target_box.box()
        row = selector.row(align=True)
        if settings.product_object:
            row.prop(settings, "product_object", text="")
            row.operator("jopex.select_object", text="", icon='EYEDROPPER')
        else:
            row.operator("jopex.select_object", text="Click to Select Object", icon='EYEDROPPER')
        
        layout.separator()
        
        row = layout.row(align=True)
        row.scale_y = 1.5
        row.menu("JOPEX_MT_quick_presets", text="QUICK PRESETS", icon='PRESET')
        
        layout.separator()
        
        row = layout.row(align=True)
        row.scale_y = 1.2
        row.operator("jopex.add_light", text="+ ADD NEW LIGHT", icon='ADD')
        
        row = layout.row(align=True)
        row.operator("jopex.clear_all_lights", text="Clear All Lights", icon='X')
        row.operator("jopex.reset_preset", text="Reset", icon='LOOP_BACK')
        
        row = layout.row(align=True)
        row.operator("jopex.save_preset", text="Save Preset", icon='FILE_TICK')
        row.menu("JOPEX_MT_load_preset", text="Load Preset", icon='FILE_FOLDER')

class JOPEX_PT_active_lights(Panel):
    bl_label = "ACTIVE LIGHTS"
    bl_idname = "JOPEX_PT_active_lights"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Jopex Light Studio"
    bl_parent_id = "JOPEX_PT_main"
    
    def draw(self, context):
        layout = self.layout
        settings = context.scene.jopex_settings
        
        if not settings.lights:
            box = layout.box()
            box.label(text="No active lights", icon='INFO')
            return
        
        for i, light in enumerate(settings.lights):
            obj = bpy.data.objects.get(light.name)
            if not obj:
                continue
            
            is_active = (context.active_object == obj)
            
            card = layout.box()
            header = card.row(align=True)
            
            header.prop(light, "light_type", text="", icon_only=True)
            
            if is_active:
                header.prop(light, "name", text="", icon='EVENT_A')
            else:
                header.prop(light, "name", text="", icon='NONE')
                
            icon = 'HIDE_OFF' if light.enabled else 'HIDE_ON'
            op = header.operator("jopex.toggle_light", text="", icon=icon, emboss=False)
            op.light_index = i
            
            op = header.operator("jopex.toggle_details", text="", icon='PREFERENCES', emboss=False)
            op.light_index = i
            
            rig_icon = 'CONSTRAINT' if light.use_rig_control else 'UNLINKED'
            op = header.operator("jopex.toggle_rig_control", text="", icon=rig_icon, emboss=False)
            op.light_index = i
            
            op = header.operator("jopex.remove_light", text="", icon='TRASH', emboss=False)
            op.light_index = i
            
            if light.show_details:
                controls = card.box()
                row = controls.row(align=True)
                row.prop(light, "power", text="Power", slider=True)
                row = controls.row(align=True)
                row.prop(light, "color", text="Color")
                row = controls.row(align=True)
                row.prop(light, "distance", text="Dist")
                row.prop(light, "angle", text="Angle")
                row = controls.row(align=True)
                row.prop(light, "size", text="Size")
                row.prop(light, "height", text="Height")
                row = controls.row(align=True)
                row.prop(light, "use_shadow", text="Shadow", icon='SHADING_RENDERED')
                if light.use_shadow:
                    row.prop(light, "shadow_softness", text="Softness", slider=True)

class JOPEX_PT_master_controls(Panel):
    bl_label = "MASTER CONTROLS"
    bl_idname = "JOPEX_PT_master_controls"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Jopex Light Studio"
    bl_parent_id = "JOPEX_PT_main"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        settings = context.scene.jopex_settings
        
        box = layout.box()
        col = box.column(align=True)
        
        row = col.row(align=True)
        row.prop(settings, "master_power", text="Power", icon='LIGHT', slider=True)
        
        row = col.row(align=True)
        row.prop(settings, "master_distance", text="Distance", icon='ARROW_LEFTRIGHT', slider=True)
        
        row = col.row(align=True)
        row.prop(settings, "master_angle_offset", text="Angle", icon='FILE_REFRESH', slider=True)
        
        row = col.row(align=True)
        row.prop(settings, "master_height_offset", text="Height", icon='ARROW_LEFTRIGHT', slider=True)
        
        row = col.row(align=True)
        row.prop(settings, "master_scale", text="Scale", icon='FULLSCREEN_ENTER', slider=True)
        
        row = col.row(align=True)
        row.prop(settings, "master_color", text="Color", icon='COLOR')
        
        row = col.row(align=True)
        row.prop(settings, "master_light_type", text="Type", icon='LIGHT_DATA')

class JOPEX_PT_hdri(Panel):
    bl_label = "HDRI ENVIRONMENT"
    bl_idname = "JOPEX_PT_hdri"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Jopex Light Studio"
    bl_parent_id = "JOPEX_PT_main"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        settings = context.scene.jopex_settings
        
        box = layout.box()
        
        row = box.row(align=True)
        row.prop(settings, "hdri_enabled", text="", icon='HIDE_OFF' if settings.hdri_enabled else 'HIDE_ON')
        row.label(text="HDRI MAP", icon='TEXTURE')
        if settings.hdri_path:
            row.label(text=os.path.basename(settings.hdri_path), icon='FILE_IMAGE')
        row.operator("jopex.load_hdri", text="", icon='FILE_FOLDER')
        
        if settings.hdri_enabled and settings.hdri_path:
            col = box.column(align=True)
            col.separator()
            
            col.label(text="MAIN CONTROLS", icon='LIGHT')
            col.prop(settings, "hdri_strength", text="Strength", slider=True)
            col.prop(settings, "hdri_rotation", text="Rotation", slider=True)
            
            col.separator()
            
            # Show Background toggle — simple on/off, no strength tweak
            bg_icon = 'HIDE_OFF' if settings.hdri_background_visible else 'HIDE_ON'
            row = col.row(align=True)
            row.prop(settings, "hdri_background_visible", text="Show Background", icon=bg_icon)
            
        elif not settings.hdri_path:
            box.label(text="No HDRI loaded. Click folder icon to load.", icon='INFO')

class JOPEX_PT_ambience(Panel):
    bl_label = "AMBIENCE LIGHT"
    bl_idname = "JOPEX_PT_ambience"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Jopex Light Studio"
    bl_parent_id = "JOPEX_PT_main"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        settings = context.scene.jopex_settings
        
        box = layout.box()
        row = box.row(align=True)
        row.prop(settings, "ambience_enabled", text="", icon='HIDE_OFF' if settings.ambience_enabled else 'HIDE_ON')
        row.label(text="AMBIENCE", icon='WORLD')
        
        if settings.ambience_enabled:
            col = box.column(align=True)
            col.separator()
            col.prop(settings, "ambience_strength", text="Strength", slider=True)
            col.prop(settings, "ambience_color", text="Color")

class JOPEX_PT_volume(Panel):
    bl_label = "VOLUME SCATTER"
    bl_idname = "JOPEX_PT_volume"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Jopex Light Studio"
    bl_parent_id = "JOPEX_PT_main"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        settings = context.scene.jopex_settings
        
        box = layout.box()
        row = box.row(align=True)
        row.prop(settings, "volume_enabled", text="", icon='HIDE_OFF' if settings.volume_enabled else 'HIDE_ON')
        row.label(text="VOLUME", icon='VOLUME_DATA')
        
        if settings.volume_enabled:
            col = box.column(align=True)
            col.separator()
            col.prop(settings, "volume_density", text="Density", slider=True)
            col.prop(settings, "volume_anisotropy", text="Anisotropy", slider=True)
            col.prop(settings, "volume_color", text="Color")
            col.prop(settings, "volume_scale", text="Scale", slider=True)

class JOPEX_PT_support_contact(Panel):
    bl_label = ""
    bl_idname = "JOPEX_PT_support_contact"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Jopex Light Studio"
    bl_parent_id = "JOPEX_PT_main"
    bl_options = {'HIDE_HEADER'}
    
    def draw(self, context):
        layout = self.layout
        box = layout.box()
        col = box.column(align=True)
        col.alignment = 'CENTER'
        
        row = col.row(align=True)
        row.alignment = 'CENTER'
        row.label(text="Developed By")
        
        row = col.row(align=True)
        row.alignment = 'CENTER'
        row.label(text="Jopex Creatives", icon='USER')
        
        row = col.row(align=True)
        row.alignment = 'CENTER'
        row.label(text="jopexcreatives@gmail.com")

# ==============================================
# REGISTRATION
# ==============================================

classes = [
    JopexLightSettings,
    JopexStudioSettings,
    JOPEX_MT_quick_presets,
    JOPEX_MT_load_preset,
    JOPEX_OT_quick_preset_3point,
    JOPEX_OT_quick_preset_product,
    JOPEX_OT_quick_preset_portrait,
    JOPEX_OT_quick_preset_cinematic,
    JOPEX_OT_quick_preset_dramatic,
    JOPEX_OT_quick_preset_outdoor,
    JOPEX_OT_add_light,
    JOPEX_OT_load_hdri,
    JOPEX_OT_toggle_rig_control,
    JOPEX_OT_toggle_light,
    JOPEX_OT_toggle_details,
    JOPEX_OT_select_object,
    JOPEX_OT_remove_light,
    JOPEX_OT_clear_all_lights,
    JOPEX_OT_reset_preset,
    JOPEX_OT_save_preset,
    JOPEX_OT_load_preset,
    JOPEX_OT_update_master_power,
    JOPEX_OT_apply_global_settings,
    JOPEX_OT_apply_master_scale,
    JOPEX_OT_apply_global_type,
    JOPEX_OT_apply_global_color,
    JOPEX_PT_main,
    JOPEX_PT_quick_presets,
    JOPEX_PT_active_lights,
    JOPEX_PT_master_controls,
    JOPEX_PT_hdri,
    JOPEX_PT_ambience,
    JOPEX_PT_volume,
    JOPEX_PT_support_contact,
]

def register():
    global custom_icons
    custom_icons = bpy.utils.previews.new()
    addon_dir = os.path.dirname(__file__)
    logo_path = os.path.join(addon_dir, "jopexlogo.png")
    if os.path.exists(logo_path):
        custom_icons.load("jopex_logo", logo_path, 'IMAGE')

    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.jopex_settings = PointerProperty(type=JopexStudioSettings)
    bpy.app.handlers.load_post.append(load_post_handler)
    bpy.app.handlers.depsgraph_update_post.append(scene_update_post_handler)
    
    print("\n" + "="*60)
    print("JOPEX LIGHT STUDIO v1.0.0")
    print("Professional Lighting Addon for Blender")
    print("Developed By Jopex Creatives")
    print("Contact: jopexcreatives@gmail.com")
    print("="*60 + "\n")

def unregister():
    global custom_icons
    if custom_icons is not None:
        bpy.utils.previews.remove(custom_icons)
        custom_icons = None
        
    if load_post_handler in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(load_post_handler)
    if scene_update_post_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(scene_update_post_handler)
    try:
        delattr(bpy.types.Scene, 'jopex_settings')
    except Exception as e:
        pass
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception as e:
            pass

if __name__ == "__main__":
    register()