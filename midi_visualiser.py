import cv2
import ffmpeg
from idlelib.tooltip import Hovertip
import math
import os
import pretty_midi
import pygame as pg
import tkinter as tk
import tkinter.filedialog
import tkinter.messagebox
import tkinter.ttk as ttk
import configparser
import random
import re
import shutil
import subprocess


# pip install git+https://github.com/vishnubob/python-midi@feature/python3
import midi
import note

DEFAULT_SCREEN_WIDTH = 1250
DEFAULT_SCREEN_HEIGHT = 600

pg.init()
screen = pg.display.set_mode((DEFAULT_SCREEN_WIDTH, DEFAULT_SCREEN_HEIGHT), pg.RESIZABLE)
pg.display.set_caption("LuckyLootCrate's MIDI Visualiser")
FONT = pg.font.SysFont('Times New Roman', 20)

def is_note_on(event):
    """
    Sometimes Note Offs are marked by
    event.name = "Note On" and velocity = 0.
    That's why we have to check both event.name and
    velocity.
    """
    velocity = event.data[1]
    return event.name == "Note On" and velocity > 0

def calculate_note_times(note_tracks, tempo_bpm, resolution):
    """
    Calculate start_time and end_time for all notes.
    This only works if the MIDI file does not contain
    any tempo changes.
    """
    for t in note_tracks:
        for pl in t:
            for n in pl:
                n.calculate_start_and_end_time(tempo_bpm, resolution)

def get_pitch_min_max(note_tracks):
    """
    In order not to waste space,
    we may want to know in advance what the highest and lowest
    pitches of the MIDI notes are.
    """
    pitch_min = 128
    pitch_max = 0
    for t in note_tracks:
        for pitch_list in t:
            for note in pitch_list:
                pitch = note.pitch
                if pitch > pitch_max:
                    pitch_max = pitch
                if pitch < pitch_min:
                    pitch_min = pitch
    return pitch_min, pitch_max

def get_maximum_time(note_tracks):
    """
    Determines the largest value of end_time
    among all notes. This is required to know
    when the video should end.
    """
    maximum_time = -999999.9
    for t in note_tracks:
        for pitch_list in t:
            if pitch_list != []:
                if pitch_list[-1].end_time > maximum_time:
                    maximum_time = pitch_list[-1].end_time
    return maximum_time


def is_note_active(note, time):
    """
    Notes that are currently playing may be treated differently.
    """

    if note.start_time <= time and note.end_time >= time and time != 0:
        return True
    else:
        return False

def is_chord_active(chord, time):
    if chord.start_time <= time and chord.end_time > time and time != 0:
        return True
    else:
        return False

def get_config(filename):
    """
    All settings are stored in an external text file.
    """
    config = configparser.ConfigParser()
    config.read(filename)
    return config

def delete_and_create_folders():
    """
    Clean everything up first.
    """
    foldernames = ["./tmp_images"]
    for f in foldernames:
        if os.path.isdir(f):
            shutil.rmtree(f)
        os.mkdir(f)


def convert_hex_to_rgb(hexcode):
    if hexcode.startswith('#'):
        h = hexcode[1:]
    return [int(h[i:i+2], 16) for i in range(0, len(h), 2)]

def convert_rgb_to_hex(r, g, b):
    return '#' + ''.join((hex(int(i))[2:]).zfill(2) for i in (r,g,b))

def calculate_lighter_shade(hexcode, proportion=0.5):
    r, g, b = convert_hex_to_rgb(hexcode)

    # Lightens the colours by a fixed proportion
    if proportion >= 0:
        x, y, z = 255-r, 255-g, 255-b
        x, y, z = [round(i*proportion) for i in (x,y,z)]
        r, g, b = r+x, g+y, b+z

    # Darkens the colours if the proportions are negative
    else:
        r, g, b = [round(i*(1 - abs(proportion))) for i in (r,g,b)]

    return convert_rgb_to_hex(r,g, b)

def is_chord_valid(chord):
    return bool(re.match(r'^.+\[[a-i]\.?\]$', chord))

def get_chords(filename):
    chords = []
    with open(filename, 'r') as f:
        for line in f.read().splitlines():
            for chord in line.split(', '):
                chord = chord.replace(',', '')
                if chord == '':
                    continue
                assert is_chord_valid(chord), f"{chord} is not valid!"
                chords.append(chord)
        return chords

class Theme:
    def __init__(self, name, note_colors, bg_color, margin_color="000000"):
        self.name = name
        self.note_colors = ['#' + color for color in note_colors]
        self.current_colors = self.note_colors

        if len(bg_color) == 2:
            self.bg_color = ['#' + color for color in bg_color]
        else:
            self.bg_color = '#' + bg_color
            
        self.margin_color = '#' + margin_color

    def __repr__(self):
        return f"Theme({self.name})"

THEMES = {
    "Default": Theme("Default", "f4743b,E6AF2E,94b0da,f0544f,BC2C1A,f49e4c,2191fb,1c5253,70ae6e,beee62".split(','), bg_color=("000048", "000032"), margin_color="000024"),
    "Classic": Theme("Classic", "7a8158,816858,5e8158,587081,5e5881,7a5881,815868,415f53".split(','), bg_color="000000"),
    "Obsidian": Theme("Obsidian", "EC7600,678CB1,FF0000,93C763,E0E2E4,66747B".split(','), bg_color="293134", margin_color="1f2426"),
    "Darcula": Theme("Darcula", "A9B7C6,CC7832,8888C6,008080,007E09,BBBBBB,FF6B68".split(','), bg_color="2B2B2B", margin_color="191919"),
    "Monochrome": Theme("Monochrome", 'FFFFFF,BBBBBB,707070,303030'.split(','), bg_color="000000"),
    "Discord": Theme("Discord", "7289da,43b581,f04747,faa61a".split(','), bg_color="36393f", margin_color="202225"),
    "veryserioussong": Theme("veryserioussong", "7b6c43,2b765e,4f6943,6d524f,724e3a,42504f".split(','), bg_color="171d19"),
    "Kirby": Theme("Kirby", "d57cab,c6e578,8670e9,919bf2,d77a70,da9761,aee17f,68e8e8".split(','), bg_color="1e0561"),
    "Medly": Theme("Medly", "eee721,fd54a3,c579ff,f58700".split(','), bg_color=("001634", "013d8b"), margin_color="001326"),
    "MIDI": Theme("MIDI", "000000,ffffff".split(','), bg_color="000000")
}

# medly colours
# piano pink: fd54a3
# bass purple: f58700
# drum orange: f58700
# synth yellow: eee721

    

class Chord:
    def __init__(self, text, start_time, end_time, app):
        self.text = text
        self.start_time = start_time
        self.end_time = end_time
        self.app = app
        self.font = pg.font.SysFont('Times New Roman', 15)
        self.width, self.height = self.font.size(text)

    def __repr__(self):
        return f"Chord({self.text}, {self.start_time}, {self.end_time})"
        
class Visualisation:
    def __init__(self, name, app):
        self.name = name
        self.app = app

    @property
    def font_size_proportion(self):
        """The font size of the chords in proportion to the size of the entire screen."""

        # Font size in respect to changes in screen height
        chord_margin = self.app.edge_margin_proportion * self.app.chord_margin_proportion
        height_proportion = self.app.edge_margin_proportion - (self.app.edge_margin_proportion * self.app.chord_margin_proportion * 2)
        return height_proportion

        # Font size in respect to changes in screen width
        #return min(height_proportion, width_proportion)

class SynthesiaVisualisation(Visualisation):
    """A synthesia style visualisation which involves notes falling from the top of the screen. The current time marker is near the bottom."""

    name = "Synthesia"
    
    def __init__(self, app):
        self.app = app
        self.activation_proportion = 0.1

    @property
    def pixels_per_second(self):
        return self.app.screen_height / (self.app.note_travel_time)

    @property
    def pixels_to_remove_from_notes_x(self):
        return self.app.pixels_to_remove_between_simultaneous_notes

    @property
    def pixels_to_remove_from_notes_y(self):
        return self.app.pixels_to_remove_between_consecutive_notes

    @property
    def margin_x(self):
        return self.app.screen_width * self.app.edge_margin_proportion

    @property
    def chord_margin_x(self):
        return

    def draw_chords(self, current_chords, time, bottom_edge_timestamp, top_edge_timestamp):

        font = pg.font.SysFont("Verdana", round(self.font_size_proportion * self.app.screen_height))
        margin_width = self.app.edge_margin_proportion * self.app.screen_width

        # Since surfaces don't have positions, you need to track where the topleft should be depending on the margin surface
        margin, topleft = {
            'Top': (self.right_margin, (self.app.screen_width-margin_width, 0)),
            'Bottom': (self.left_margin, (0, 0))
        }[self.app.chord_side]

        # If there is a gradient, choose the first color
        if len(app.theme.bg_color) == 2:
            bg_color = app.theme.bg_color[0]
        else:
            bg_color = app.theme.bg_color
        
        for chord in current_chords:
            chord_height = font.size(chord.text)[1]
            
            if self.app.chord_style in ['Dynamic', 'Dynamic Inline']:
                duration = chord.end_time - chord.start_time

                if self.app.chord_style == 'Dynamic':
                    chord_offset = (duration / 2) * self.pixels_per_second
                else:
                    chord_offset = duration * self.pixels_per_second

                # Center the chord
                chord_offset -= (chord_height // 2)
                y_pos = round(-(chord.end_time - top_edge_timestamp) * self.pixels_per_second) + chord_offset
                
                chord_color = calculate_lighter_shade(bg_color, proportion=0.2)
                if is_chord_active(chord, time):
                    chord_color = calculate_lighter_shade(chord_color, self.app.activation_brightness)
                rendered_chord = font.render(chord.text, False, chord_color)
                screen.blit(rendered_chord, rendered_chord.get_rect(y=y_pos, centerx=margin.get_rect(topleft=topleft).centerx))
                
            elif self.app.chord_style == 'Static':

                if is_chord_active(chord, time):
                    chord_color = calculate_lighter_shade(bg_color, self.app.activation_brightness)
                    rendered_chord = font.render(chord.text, False, chord_color)
                    screen.blit(rendered_chord, rendered_chord.get_rect(
                        centery=margin.get_rect(topleft=topleft).centery,
                        centerx=margin.get_rect(topleft=topleft).centerx)
                    )

    def draw_notes(self, current_notes, time, bottom_edge_timestamp, top_edge_timestamp, pitch_min, pitch_max, width, roundedness):
        """
        For each frame, this function is called.
        The notes which appear in this image (current_notes) have
        already been selected.

        3 * self.margin_x is used because 2 of the margin widths are needed between the notes and the actual edges of the screen.
        However, the spare margin width is used so that the notes can be spaced half a margin gap between the border.
        """

        if self.app.should_draw_margin:
            margin_multiplier = 1.5
        else:
            margin_multiplier = 1

        # An extra one is needed to make space for the margin
        no_of_columns = pitch_max - pitch_min + 1
        column_width = (self.app.screen_width - (2.0 * self.margin_x * margin_multiplier)) / no_of_columns
        note_width = round(max(1, column_width - self.pixels_to_remove_from_notes_x))

        for note in current_notes:
            col_no = note.pitch - pitch_min
            x_pos = round((self.margin_x*margin_multiplier) + (col_no * column_width))
            y_pos = round(-(note.end_time - top_edge_timestamp) * self.pixels_per_second)
            y_height = max(1, round((note.end_time - note.start_time) * self.pixels_per_second - self.pixels_to_remove_from_notes_y))

            # Note colors
            note_color = self.app.track_colors[note.track]
            if is_note_active(note, time):
                note_color = calculate_lighter_shade(note_color, self.app.activation_brightness)

            pg.draw.rect(screen, note_color, [x_pos, y_pos, note_width, y_height], width=width, border_radius=roundedness)

    def draw_time_marker(self):
        """This will draw the time marker (where notes will appear to get activated)"""

        time_marker = pg.Surface((self.app.screen_width, 1), pg.SRCALPHA)
        time_marker.fill((255, 255, 255, 100))
        screen.blit(time_marker, (0, self.app.screen_height * (1 - self.activation_proportion)))

    def draw_margin(self, not_hidden=True):
        """This will draw the margins onto surfaces, so that they can become transparent when disabled."""
        
        margin_width = self.app.edge_margin_proportion * self.app.screen_width
        
        self.right_margin = pg.Surface((margin_width, self.app.screen_height))
        self.right_margin.fill(self.app.theme.margin_color)
        self.left_margin = pg.Surface((margin_width, self.app.screen_height))
        self.left_margin.fill(self.app.theme.margin_color)

        if not_hidden:
            screen.blit(self.right_margin, (self.app.screen_width-margin_width, 0))
            screen.blit(self.left_margin, (0, 0))

    def draw_chord_lines(self, current_chords, entry_timestamp):
        for chord in current_chords:
            
            # Don't draw a line for empty chords for this specific style
            if self.app.chord_style == "Dynamic Inline" and not chord.text:
                continue

            # Display when the chord ends for the last chord
            if self.app.chord_style == "Dynamic" and chord == self.app.chords[-1]:
                self.draw_chord_line(round(-(chord.end_time - entry_timestamp) * self.pixels_per_second))
            
            self.draw_chord_line(round(-(chord.start_time - entry_timestamp) * self.pixels_per_second))
   
    def draw_chord_line(self, y_pos):
        """Each line will show where each chord begins."""
        
        chord_line = pg.Surface((self.app.screen_width, 1), pg.SRCALPHA)
        chord_line.fill((255, 255, 255, 50))
        screen.blit(chord_line, (0, y_pos))
         
class ClassicVisualisation(Visualisation):
    """The default visualisation which involves scrolling notes from right to left. The time_marker is in the center."""

    name = "Classic"
    
    def __init__(self, app):        
        self.app = app
        self.activation_proportion = 0.5

    @property
    def pixels_per_second(self):
        return self.app.screen_width / (self.app.note_travel_time)

    @property
    def pixels_to_remove_from_notes_x(self):
        return self.app.pixels_to_remove_between_consecutive_notes

    @property
    def pixels_to_remove_from_notes_y(self):
        return self.app.pixels_to_remove_between_simultaneous_notes
    
    @property
    def margin_y(self):
        return self.app.screen_height * self.app.edge_margin_proportion

    @property
    def chord_y_pos(self):
        return (self.app.screen_height - self.margin_y) + (self.margin_y * self.app.chord_margin_proportion)
        
    def draw_chords(self, current_chords, time, left_edge_timestamp, right_edge_timestamp):

        font = pg.font.SysFont("Verdana", round(self.font_size_proportion * self.app.screen_height))
        margin_height = self.app.edge_margin_proportion * self.app.screen_height

        # Since surfaces don't have positions, you need to track where the topleft should be depending on the margin surface
        margin, topleft = {
            'Top': (self.top_margin, (0, 0)),
            'Bottom': (self.bottom_margin, (0, self.app.screen_height-margin_height))
        }[self.app.chord_side]

        # If there is a gradient, choose the first color
        if len(app.theme.bg_color) == 2:
            bg_color = app.theme.bg_color[0]
        else:
            bg_color = app.theme.bg_color
        
        for chord in current_chords:
            chord_width = font.size(chord.text)[0]
            
            if self.app.chord_style in ['Dynamic', 'Dynamic Inline']:
                duration = chord.end_time - chord.start_time
                
                if self.app.chord_style == 'Dynamic':
                    chord_offset = (duration / 2) * self.pixels_per_second
                else:
                    chord_offset = 0

                # Center the chord
                chord_offset -= (chord_width // 2)
                x_pos = round((chord.start_time - left_edge_timestamp) * self.pixels_per_second) + chord_offset

                chord_color = calculate_lighter_shade(bg_color, proportion=0.2)
                if is_chord_active(chord, time):
                    chord_color = calculate_lighter_shade(chord_color, self.app.activation_brightness)
                rendered_chord = font.render(chord.text, False, chord_color)
                screen.blit(rendered_chord, rendered_chord.get_rect(x=x_pos, centery=margin.get_rect(topleft=topleft).centery))

            elif self.app.chord_style == 'Static':
                first_quadrant = self.app.screen_width // 4

                # Centred within the 4th quadrant
                x_pos = (first_quadrant // 2) - (chord_width // 2)

                if is_chord_active(chord, time):
                    chord_color = calculate_lighter_shade(bg_color, self.app.activation_brightness)
                    rendered_chord = font.render(chord.text, False, chord_color)
                    screen.blit(rendered_chord, rendered_chord.get_rect(x=x_pos, centery=margin.get_rect(topleft=topleft).centery))
        
        
    def draw_notes(self, current_notes, time, left_edge_timestamp, right_edge_timestamp, pitch_min, pitch_max, width, roundedness):
        """
        For each frame, this function is called.
        The notes which appear in this image (current_notes) have
        already been selected.

        3 * self.margin_y is used because 2 of the margin heights are needed between the notes and the actual edges of the screen.
        However, the spare margin height is used so that the notes can be spaced half a margin gap between the border.
        """

        if self.app.should_draw_margin:
            margin_multiplier = 1.5
        else:
            margin_multiplier = 1

        # An extra one is needed to make space for the margin
        no_of_rows = pitch_max - pitch_min + 1 
        row_height = (self.app.screen_height - (2 * self.margin_y * margin_multiplier)) / no_of_rows
        note_height = round(max(1, row_height - self.pixels_to_remove_from_notes_y))

        # Notes are drawn from low pitch to high pitch
        for note in current_notes:
            row_no = note.pitch - pitch_min

            # You subtract note_height since the margin was previously calculated from the bottom of the screen to the top of the note
            y_pos = round((self.app.screen_height - (self.margin_y*margin_multiplier) - note_height) - (row_no * row_height))
                
            x_pos = round((note.start_time - left_edge_timestamp) * self.pixels_per_second)
            x_length = max(1, round((note.end_time - note.start_time) * self.pixels_per_second - self.pixels_to_remove_from_notes_x))

            # Note colors
            note_color = self.app.track_colors[note.track]
            if is_note_active(note, time):
                note_color = calculate_lighter_shade(note_color, self.app.activation_brightness)

            """Opacity is too slow lol (and also gives uninteresting results)"""
            #note_rect = pg.Surface((x_length, note_height))
            #note_rect.set_alpha(self.app.alpha)
            #note_rect.fill(note_color)
            #screen.blit(note_rect, (x_pos, y_pos))
            
            pg.draw.rect(screen, note_color, [x_pos, y_pos, x_length, note_height], width=width, border_radius=roundedness)
        
    def draw_time_marker(self):
        """This will draw the time marker (where notes will appear to get activated)"""
        
        time_marker = pg.Surface((1, self.app.screen_height), pg.SRCALPHA)
        time_marker.fill((255, 255, 255, 100))
        screen.blit(time_marker, (self.app.screen_width * self.activation_proportion, 0))

    def draw_chord_lines(self, current_chords, exit_timestamp):
        for chord in current_chords:
            
            # Don't draw a line for empty chords for this specific style
            if self.app.chord_style == "Dynamic Inline" and not chord.text:
                continue

            # Display when the chord ends for the last chord
            if self.app.chord_style == "Dynamic" and chord == self.app.chords[-1]:
                self.draw_chord_line(round((chord.end_time - exit_timestamp) * self.pixels_per_second))
            
            self.draw_chord_line(round((chord.start_time - exit_timestamp) * self.pixels_per_second))
            
    def draw_chord_line(self, x_pos):
        """Each line will show where each chord begins."""
        
        chord_line = pg.Surface((1, self.app.screen_height), pg.SRCALPHA)
        chord_line.fill((255, 255, 255, 50))
        screen.blit(chord_line, (x_pos, 0))

    def draw_margin(self, not_hidden=True):
        """This will draw the margins onto surfaces, so that they can become transparent when disabled."""
        
        margin_height = self.app.edge_margin_proportion * self.app.screen_height
        
        self.top_margin = pg.Surface((self.app.screen_width, margin_height))
        self.top_margin.fill(self.app.theme.margin_color)
        self.bottom_margin = pg.Surface((self.app.screen_width, margin_height))
        self.bottom_margin.fill(self.app.theme.margin_color)

        if not_hidden:
            screen.blit(self.top_margin, (0, 0))
            screen.blit(self.bottom_margin, (0, self.app.screen_height-margin_height))

class ForesightVisualisation(ClassicVisualisation):

    name = "Foresight"

    def __init__(self, app):        
        self.app = app
        self.activation_proportion = 0.125

class HindsightVisualisation(ClassicVisualisation):

    name = "Hindsight"

    def __init__(self, app):        
        self.app = app
        self.activation_proportion = 0.875

class StaticVisualisation(ClassicVisualisation):

    name = "Static"

    def __init__(self, app):        
        self.app = app
        self.activation_proportion = 0

    def move_time_marker(self, dt):
        self.activation_proportion += (dt * self.pixels_per_second) / self.app.screen_width

        if self.activation_proportion >= 1:
            self.activation_proportion -= 1

class DriftVisualisation(ClassicVisualisation):

    name = "Drift"

    def __init__(self, app):        
        self.app = app
        self.activation_proportion = 0

    def move_time_marker(self, dt):
        self.activation_proportion += (dt * self.pixels_per_second * 0.75) / self.app.screen_width

        if self.activation_proportion >= 1:
            self.activation_proportion -= 1


VISUALISATIONS = [ClassicVisualisation, SynthesiaVisualisation, ForesightVisualisation, HindsightVisualisation, StaticVisualisation, DriftVisualisation]
VISUALISATION_NAME_DCT = {vis.name:vis for vis in VISUALISATIONS}


class VisualisationRunner:
    def __init__(self, app, visualisation):
        self.app = app
        self.visualisation = visualisation
        self.has_initialised_export = False
        
    @property
    def current_to_exit_time(self):
        """How long it takes for a note to travel from the current time until exiting."""
        
        return self.app.note_travel_time * self.visualisation.activation_proportion

    @property
    def entry_to_current_time(self):
        """How long it takes for a note to travel from entering to the current time."""
        
        return self.app.note_travel_time * (1 - self.visualisation.activation_proportion)
        
    def init_video(self):
        """This will activate all the settings necessary before you start the visualisation"""

        # Reset note colors when selecting new theme
        self.app.track_colors = {}
        
        self.app.note_tracks, self.app.tempo_bpm, self.app.resolution = self.app.read_midi(self.app.filename)
        calculate_note_times(self.app.note_tracks, self.app.tempo_bpm, self.app.resolution)
        self.app.chords = self.app.fetch_chords()
        self.app.play_from_start()
            
        # Calculate the min and max pitches for the new MIDI track
        self.pitch_min, self.pitch_max = get_pitch_min_max(self.app.note_tracks)
        config = self.app.config

        # Calculate the end time for the new MIDI track
        self.app.end_time = get_maximum_time(self.app.note_tracks)
        self.clear_notes()

    def clear_notes(self):
        """This function is used so that the notes can be recalculated to be put on screen."""

        self.current_note_indices = [[0 for i in range(128)] for k in range(len(self.app.note_tracks))]

    def export_video(self):
        if not self.has_initialised_export:
            self.init_video()
            self.has_initialised_export = True
            self.app.time = self.app.start_time
            delete_and_create_folders()
            self.frame = 0
            
        else:
    
            dt = 1 / self.app.frame_rate # time elapsed between frames

            if self.app.notes_end_offscreen:
                end_time = self.app.end_time + self.current_to_exit_time
            else:
                end_time = self.app.end_time
            
            # So that the last frame isn't skipped
            if self.app.time - dt <= end_time:
                print(f"Current: {self.app.time:.2f}\tFrame: {self.frame:04}\tEnd time: ({end_time:.2f})")

                # Timestamps of the very edges of the screen
                self.exit_timestamp = self.app.time - self.current_to_exit_time
                self.entry_timestamp = self.app.time + self.entry_to_current_time

                self.get_current_items_on_screen()
                self.draw_frame()

                if self.visualisation.name in ["Static", "Drift"]:
                    self.visualisation.move_time_marker(dt)
                    self.clear_notes()

                self.save_current_frame()
            else:
                self.convert_to_video()

    def convert_to_video(self):
        self.app.exporting_video = False
        self.has_initialised_export = False
        print("Done! Converting to video...")
        self.run_ffmpeg()
        print("All complete!")

    def run_ffmpeg(self):
        """
        Convert all images into a video.
        """

        """
        (
            ffmpeg
            .input("./tmp_images/%08d.jpg")
            .filter('fps', fps=self.app.frame_rate, round='up')
        """ 
        
        
        call_list = []
        call_list.append("ffmpeg")
        call_list.append("-r")
        call_list.append(f"{self.app.frame_rate}")
        call_list.append("-f")
        call_list.append("image2")
        call_list.append("-i")
        call_list.append("./tmp_images/%08d.jpg")

        # Add audio
        #call_list.append("-i")
        #call_list.append("audio.mp3")
        #call_list.append("-c:a copy -shortest")
        
        call_list.append("-vcodec")
        call_list.append("libx264")
        call_list.append("-crf")
        call_list.append("25")
        call_list.append("-pix_fmt")
        call_list.append("yuv420p")
        call_list.append("-vf")
        call_list.append("crop=trunc(iw/2)*2:trunc(ih/2)*2")
        call_list.append("-y") # Always overwrite
        call_list.append(self.app.video_path)

        print(call_list)
        subprocess.call(call_list)
                    
      
    def draw_video(self, dt, play_sound):
        if not self.app.has_initialised_video:
            self.init_video()
            self.app.has_initialised_video = True

            if play_sound:
                pg.mixer.music.load(self.app.filename)
                pg.mixer.music.play()
                self.app.loading_audio = True

        else:
            # Timestamps of the very edges of the screen
            self.entry_timestamp = self.app.time + self.entry_to_current_time
            self.exit_timestamp = self.app.time - self.current_to_exit_time

            self.get_current_items_on_screen()
            self.draw_frame()

            if self.app.notes_end_offscreen:
                end_time = self.app.end_time + self.current_to_exit_time
            else:
                end_time = self.app.end_time


            if self.app.time >= end_time:
                self.app.is_paused = True
                self.app.time = end_time

            if not self.app.is_paused or self.app.in_playback_mode:
                self.app.time += (dt / 1000)

                if self.visualisation.name in ["Static", "Drift"]:
                    self.visualisation.move_time_marker(dt / 1000)
                    self.clear_notes()

    def draw_frame(self):
        rounded_options = {"Not Rounded": 0, "Slightly Rounded": 3, "Very Rounded": 8}
        
        self.visualisation.draw_notes(
            self.app.current_notes,
            self.app.time,
            self.exit_timestamp,
            self.entry_timestamp,
            self.pitch_min,
            self.pitch_max,
            0 if self.app.are_notes_filled else 1,
            rounded_options[self.app.roundedness]
        )

        if self.app.time_marker_enabled:
            self.visualisation.draw_time_marker()

        if self.app.chord_lines_enabled:
            if self.visualisation.name == "Synthesia":
                timestamp = self.entry_timestamp
            else:
                timestamp = self.exit_timestamp
                
            self.visualisation.draw_chord_lines(self.app.current_chords, timestamp)

        self.visualisation.draw_margin(not_hidden=self.app.should_draw_margin)

        if not self.app.chord_style == 'Disabled':
            self.visualisation.draw_chords(
                self.app.current_chords,
                self.app.time,
                self.exit_timestamp,
                self.entry_timestamp,
            )

    def save_current_frame(self):
        screencopy = screen.copy()
        pg.image.save(screencopy, f"tmp_images/{self.frame:08}.jpg")
        self.frame += 1
        self.app.time += 1 / self.app.frame_rate
        
    def get_current_items_on_screen(self):
        """Prepares the variables for the frame to be drawn"""

        # Timestamps are in seconds
        self.app.current_notes = []
        for track_index, track in enumerate(self.app.note_tracks):
            for pitch_index in range(128):
                min_note_index = self.current_note_indices[track_index][pitch_index]
                max_note_index = len(track[pitch_index])
                for note_index in range(min_note_index, max_note_index):
                    note = track[pitch_index][note_index]

                    # Remove notes which are off the screen
                    if note.end_time < self.exit_timestamp:
                        self.current_note_indices[track_index][pitch_index] += 1

                    elif note.start_time < self.entry_timestamp:
                        self.app.current_notes.append(note)
                    else:
                        break

        self.app.current_chords = []
        for chord in self.app.chords:
            if chord.start_time < self.entry_timestamp and chord.end_time > self.exit_timestamp:
                self.app.current_chords.append(chord)
          
class Application:
    def __init__(self, config):
        self.running = True
        self.clock = pg.time.Clock()
        self.filename = None
        self.is_paused = False
        self.about_to_open_files = False
        self.has_initialised_video = False

        # Parameters
        self.note_tracks = None
        self.tempo_bpm = None
        self.resolution = None
        self.config = config

        # Margin and sizes
        self.edge_margin_proportion = float(config["edge_margin_proportion"])

        # Colors
        self.theme = THEMES[config["theme"]]

        # Notes
        self.pixels_to_remove_between_consecutive_notes = int(config["pixels_to_remove_between_consecutive_notes"])
        self.pixels_to_remove_between_simultaneous_notes = int(config["pixels_to_remove_between_simultaneous_notes"])
        self.roundedness = config["roundedness"]
        self.are_notes_filled = config["are_notes_filled"].lower() == 'true'
        self.activation_brightness = float(config["activation_brightness"])

        # Timings
        self.frame_rate = int(config["frame_rate"])
        self.seconds_before_start = float(config["seconds_before_start"])
        self.time = -self.seconds_before_start
        self.time_skip = 1 # second

        # How many seconds it takes for a note to travel across the screen
        self.default_travel_time = float(config["default_travel_time"]) # CONSTANT VALUE
        self.note_travel_time = float(config["default_travel_time"]) # CAN CHANGE

        # Controls
        self.left_key_held = False
        self.right_key_held = False

        # Chords
        self.chord_path = config["chord_path"]
        self.chord_margin_proportion = float(config["chord_margin_proportion"])
        self.chord_style = config["chord_style"]
        self.chord_side = config["chord_side"]
        self.chord_lines_enabled = config["chord_lines_enabled"].lower() == 'true'

        # Video
        self.folder_to_save = config["folder_to_save"]
        self.file_name = config["file_name"]
        self.exporting_video = False
        self.in_playback_mode = False # where you can hear the midi sound
        self.should_draw_margin = config["should_draw_margin"].lower() == 'true'
        self.time_marker_enabled = config["time_marker_enabled"].lower() == 'true'
        self.notes_end_offscreen = config["notes_end_offscreen"].lower() == 'true'

        # Visualisation
        self.visualisation = VISUALISATION_NAME_DCT[config["visualisation"]](self)
        self.render_engine = VisualisationRunner(self, self.visualisation)
        self.update_screen_size()

        # Audio
        self.loading_audio = False # So that the visualisation waits until the audio finishes loading before starting

        # Configuration
        self.last_selected_tab = 0 # Select the first tab as the default

    @property
    def start_time(self):
        return -self.seconds_before_start

    @property
    def video_path(self):
        return os.path.join(self.folder_to_save, self.file_name) + '.mp4'
        
    def update_screen_size(self):
        self.screen_width, self.screen_height = pg.display.get_surface().get_size()

    def prompt_config_change(self):
        config = {
            "visualisation": self.visualisation,
            "chord_style": self.chord_style,
            
            "edge_margin_proportion": self.edge_margin_proportion,
            "chord_margin_proportion": self.chord_margin_proportion,
            "pixels_to_remove_between_consecutive_notes": self.pixels_to_remove_between_consecutive_notes,
            "pixels_to_remove_between_simultaneous_notes": self.pixels_to_remove_between_simultaneous_notes,
            
            "are_notes_filled": self.are_notes_filled,
            "roundedness": self.roundedness,
            "should_draw_margin": self.should_draw_margin,
            "chord_side": self.chord_side,
            "chord_lines_enabled": self.chord_lines_enabled,
            "time_marker_enabled": self.time_marker_enabled,
            "activation_brightness": self.activation_brightness,
            "notes_end_offscreen": self.notes_end_offscreen,
            
            "frame_rate": self.frame_rate,
            "seconds_before_start": self.seconds_before_start,            
            "file_name": self.file_name,
            "folder_to_save": self.folder_to_save,
            "chord_path": self.chord_path,

            "last_selected_tab": self.last_selected_tab,
            "theme": self.theme,
        }
        
        app = ConfigMenu(config)
        config = app.get_configuration()
        self.update_config(config)

    def update_config(self, config):
        vis = config["visualisation"]
        self.visualisation = VISUALISATION_NAME_DCT[vis](self)
        self.chord_style = config["chord_style"]
        
        self.edge_margin_proportion = config["edge_margin_proportion"]
        self.chord_margin_proportion = config["chord_margin_proportion"]
        self.pixels_to_remove_between_consecutive_notes = config["pixels_to_remove_between_consecutive_notes"]
        self.pixels_to_remove_between_simultaneous_notes = config["pixels_to_remove_between_simultaneous_notes"]
        
        self.are_notes_filled = config["are_notes_filled"]
        self.should_draw_margin = config["should_draw_margin"]
        self.roundedness = config["roundedness"]
        self.chord_side = config["chord_side"]
        self.chord_lines_enabled = config["chord_lines_enabled"]
        self.time_marker_enabled = config["time_marker_enabled"]
        self.activation_brightness = config["activation_brightness"]
        self.notes_end_offscreen = config["notes_end_offscreen"]
        
        self.frame_rate = config["frame_rate"]
        self.seconds_before_start = config["seconds_before_start"]
        self.file_name = config["file_name"]
        self.folder_to_save = config["folder_to_save"]
        self.chord_path = config["chord_path"]

        self.last_selected_tab = config["last_selected_tab"]
        self.theme = config["theme"]

        if self.tempo_bpm is not None:

            self.chords = self.fetch_chords()
            
            # Allow for the static command to have snapped zooming features
            if self.visualisation.name == "Static":
                bps = self.tempo_bpm / 60
                beat_duration = 1 / bps
                self.note_travel_time = beat_duration * 4

        self.has_initialised_video = False
        
        
    def event_loop(self):
        for event in pg.event.get():
            if event.type == pg.QUIT:
                self.running = False
                self.quit()
                return

            mods = pg.key.get_mods()
            
            if event.type == pg.KEYDOWN:

                # Open the config menu
                if event.key == pg.K_ESCAPE:
                    
                    if not self.exporting_video:
                        config = self.prompt_config_change()
                        self.render_engine = VisualisationRunner(self, self.visualisation)
                        self.has_initialised_video = False
                        self.is_paused = True

                # Pausing
                if event.key == pg.K_SPACE:
                    self.is_paused = not self.is_paused
                
                # Ctrl + Something key bindings

                # Open a new MIDI file
                if mods and pg.KMOD_CTRL:
                    if event.key == pg.K_o:
                        if not self.exporting_video:
                            self.await_file_input()
                            self.is_paused = True
                    
                    if self.filename is not None:
                        # Zooming with keyboard
                        if event.key in [pg.K_MINUS, pg.K_DOWN]:
                            self.zoom_out()
                        if event.key in [pg.K_PLUS, pg.K_UP]:
                            self.zoom_in()
    
                        # Hold to time skip
                        if event.key == pg.K_LEFT:
                            self.left_key_held = True
                        if event.key == pg.K_RIGHT:
                            self.right_key_held = True

                        # Exporting video
                        if event.key == pg.K_s:

                            if not self.exporting_video:

                                # Ask user before potentially overwriting file
                                if os.path.isfile(self.video_path):
                                    top = tk.Tk()
                                    top.withdraw()  # hide window
                                    
                                    answer = tk.messagebox.askquestion(title="This File Exists!", message=f"A file already exists at the location {self.video_path}\nDo you want to overwrite it?")
                                    top.destroy()

                                    if answer == 'yes':
                                        self.exporting_video = True

                                else:
                                    self.exporting_video = True
                                    
                # Time skipping commands (only when notes are loaded)
                if self.filename is not None:
                    if event.key == pg.K_HOME:

                        # So that the song also restarts whenever you go back to the start in playback mode
                        if self.in_playback_mode:
                            self.has_initialised_video = False
                            
                        self.play_from_start()

                    if not self.in_playback_mode:
                        if event.key == pg.K_END:
                            self.play_from_end()
                        if event.key == pg.K_LEFT:
                            self.skip_to_nearest_previous_note()  
                        if event.key == pg.K_RIGHT:
                            self.skip_to_nearest_next_note()

                    # Play with sound lol
                    if event.key == pg.K_p:
                        self.in_playback_mode = not self.in_playback_mode
                        self.has_initialised_video = False
                        self.play_from_start()

                        if not self.in_playback_mode:
                            pg.mixer.music.unload()
                            

            if event.type == pg.KEYUP:
                if event.key == pg.K_LEFT:
                    self.left_key_held = False

                if event.key == pg.K_RIGHT:
                    self.right_key_held = False

            # Zooming in with the mouse
            if event.type == pg.MOUSEBUTTONDOWN:
                if self.filename is not None:
                    if mods and pg.KMOD_CTRL:
                        if event.button == 4:
                            self.zoom_in()
                        elif event.button == 5:
                            self.zoom_out()

    def zoom_in(self):
        if self.visualisation.name == "Static":
            self.note_travel_time /= 2
        else:
            self.note_travel_time /= 1.3
        self.render_engine.clear_notes()

    def zoom_out(self):
        if self.visualisation.name == "Static":
            self.note_travel_time *= 2
        else:
            self.note_travel_time *= 1.3
        self.render_engine.clear_notes()
        
    def handle_arrow_keys(self):
        if self.left_key_held:
            self.skip_to_nearest_previous_note()
        elif self.right_key_held:
            self.skip_to_nearest_next_note()
            
    def play_from_start(self):
        self.time = self.start_time
        self.render_engine.clear_notes()
        self.is_paused = True

        if self.visualisation.name in ["Static", "Drift"]:
            self.visualisation.activation_proportion = 0

    def play_from_end(self):
        self.time = self.end_time
        self.render_engine.clear_notes()
        self.is_paused = True
        
    def skip_to_nearest_previous_note(self):
        lst = sorted(self.current_notes, key=lambda x: x.start_time, reverse=True)

        # Allow for users to go to the very start if the recording starts before the first note
        if self.time == 0:
            self.time = self.start_time
            self.render_engine.clear_notes()
            self.is_paused = True
            return
        
        for note in lst:
            if note.start_time < self.time:
                self.time = note.start_time
                self.render_engine.clear_notes()
                self.is_paused = True
                return

    def skip_to_nearest_next_note(self):
        lst = sorted(self.current_notes, key=lambda x: x.start_time)
        
        for note in lst:
            if note.start_time > self.time:
                self.time = note.start_time
                self.render_engine.clear_notes()
                self.is_paused = True
                return

    def read_midi(self, filename):
        """
        Returns a list of tracks.
        Each track is a list containing 128 lists of notes.
        """
        midi_tracks = midi.read_midifile(filename)
        resolution = midi_tracks.resolution
        tempo_bpm = 120.0  # may be changed repeatedly in the loop
        note_tracks = []
        colors = self.theme.current_colors
        
        for t_index, t in enumerate(midi_tracks):
            notes_pitchwise = [[] for i in range(128)]
            total_ticks = 0
            for elem in t:
                total_ticks += elem.tick
                if elem.name in ["Note On", "Note Off"]:
                    pitch = elem.data[0]
                    if is_note_on(elem):
                        n = note.Note(
                            velocity=elem.data[1],
                            pitch=pitch,
                            start_ticks=total_ticks,
                            track=t_index)
                        notes_pitchwise[pitch].append(n)

                        if t_index not in self.track_colors:
                            self.track_colors[t_index] = colors[0]
                            colors = colors[1:] + [colors[0]]
                            
                    else:
                        for n in reversed(notes_pitchwise[pitch]):
                            if not n.finished:
                                n.end_ticks = total_ticks
                                n.finished = True
                            else:
                                break
                elif elem.name == "Set Tempo":
                    tempo_bpm = elem.get_bpm()
            note_tracks.append(notes_pitchwise)

        return note_tracks, tempo_bpm, resolution

    def parse_chords(self, chords, tempo_bpm):
        """Returns a list of chord objects which include their text and their starting and ending times"""

        crotchet_duration = 60 / tempo_bpm # How long a single crotchet beat takes in seconds

        CHORD_DURATIONS = {
            'a': crotchet_duration * 0.25,
            'b': crotchet_duration * 0.5,
            'c': crotchet_duration * 1,
            'd': crotchet_duration * 2,
            'e': crotchet_duration * 4,
            'f': crotchet_duration / 6,
            'g': crotchet_duration / 3,
            'h': crotchet_duration / 1.5,
            'i': crotchet_duration * 0.125
        }

        time_elapsed = 0
        chord_output = []
        
        for chord in chords:
            match = re.match('^(.+)\[(.+)\]$', chord)
            text, duration = match.group(1), match.group(2)

            if text == '!':
                text = ''

            # Dealing with dotted notes
            if duration.endswith('.'):
                chord_duration = CHORD_DURATIONS[duration[0]]
                chord_duration *= 1.5
            else:
                chord_duration = CHORD_DURATIONS[duration]

            chord = Chord(text, time_elapsed, time_elapsed+chord_duration, self)
            chord_output.append(chord)
            time_elapsed += chord_duration

        return chord_output

    def prompt_file(self):            
        """Create a Tk file dialog and cleanup when finished"""

        self.previous_file = self.filename
        top = tk.Tk()
        top.withdraw()  # hide window
        
        filename = tk.filedialog.askopenfilename(
            parent=top,
            title="Choose a MIDI file",
            filetypes=[("MIDI files", '.mid'),
                       ("MIDI files", '.midi')]
            )
        
        top.destroy()
    
        return filename

    def await_file_input(self):
        self.filename = self.prompt_file()

        if self.filename:
            self.has_initialised_video = False
            
        # If the user cancels the dialogue box, but something is already loaded, keep it
        elif self.previous_file:
            self.filename = self.previous_file
            self.render_engine.clear_notes()

    def fetch_chords(self):
        return self.parse_chords(get_chords(self.chord_path), self.tempo_bpm)

    def hide_margin(self):
        self.visualisation.top_margin.set_alpha(0)
        self.visualisation.bottom_margin.set_alpha(0)

    def draw_bg(self):
            
        if len(self.theme.bg_color) == 2:
            top_color, bottom_color = self.theme.bg_color
            
            colour_rect = pg.Surface((2, 2))
            pg.draw.line(colour_rect, top_color, (0,0), (1,0))  
            pg.draw.line(colour_rect, bottom_color, (0,1), (1,1))
            colour_rect = pg.transform.smoothscale(colour_rect, (self.screen_width, self.screen_height))  # stretch!
            screen.blit(colour_rect, (0, 0))

        else:
            screen.fill(self.theme.bg_color)
        
            
    def run(self):
        while self.running:
            dt = self.clock.tick(self.frame_rate)

            if self.loading_audio:
                dt = 0
                self.loading_audio = False
                
            self.draw_bg()
            self.update_screen_size()
            self.handle_arrow_keys()
            
            if self.filename:
                if self.exporting_video:
                    self.render_engine.export_video()
                else:
                    self.render_engine.draw_video(dt, play_sound=self.in_playback_mode)
            else:
                if self.time_marker_enabled:
                    self.render_engine.visualisation.draw_time_marker()
                self.visualisation.draw_margin(not_hidden=self.should_draw_margin)
            
            pg.display.update()
            self.event_loop()

    def quit(self):
        self.running = False
        pg.quit()

class ConfigMenu:
    vis_names = [vis.name for vis in VISUALISATIONS]
    rounded_options = ["Not Rounded", "Slightly Rounded", "Very Rounded"]
    chord_styles = ["Disabled", "Static", "Dynamic", "Dynamic Inline"]
    chord_side_options = ["Top", "Bottom"]
    frame_rates = [24, 30, 50, 60]
    theme_list = list(THEMES.keys())

    def __init__(self, config):
        """Setting the default values for the configuration options."""
        
        self.visualisation = config["visualisation"]
        self.chord_style = config["chord_style"]
        
        self.edge_proportion = config["edge_margin_proportion"]
        self.chord_proportion = config["chord_margin_proportion"]
        self.consecutive_gap = config["pixels_to_remove_between_consecutive_notes"]
        self.simultaneous_gap = config["pixels_to_remove_between_simultaneous_notes"]
        
        self.are_notes_filled = config["are_notes_filled"]
        self.should_draw_margin = config["should_draw_margin"]
        self.roundedness = config["roundedness"]
        self.chord_side = config["chord_side"]
        self.chord_lines_enabled = config["chord_lines_enabled"]
        self.time_marker_enabled = config["time_marker_enabled"]
        self.activation_brightness = config["activation_brightness"]
        self.notes_end_offscreen = config["notes_end_offscreen"]
        
        self.seconds_before_start = config["seconds_before_start"]
        self.frame_rate = config["frame_rate"]
        self.file_name = config["file_name"]
        self.folder_to_save = config["folder_to_save"]
        self.chord_path = config["chord_path"]

        self.last_selected_tab = config["last_selected_tab"]

        self.theme = config["theme"]
        self.run()

    def run(self):
        self.root = tk.Tk()
        self.root.focus_force()
        
        self.root.title("Visualisation Options")
        self.tab_control = ttk.Notebook(self.root)

        # Setting up tabs
        tab1 = ttk.Frame(self.tab_control)
        tab2 = ttk.Frame(self.tab_control)
        tab3 = ttk.Frame(self.tab_control)
        tab4 = ttk.Frame(self.tab_control)
        tab5 = ttk.Frame(self.tab_control)

        self.tab_control.add(tab1, text="Visualisation Style")
        self.tab_control.add(tab2, text="Spacing")
        self.tab_control.add(tab3, text="Appearance")
        self.tab_control.add(tab4, text="Video")
        self.tab_control.add(tab5, text="Themes")
        self.tab_control.pack(expand=1, fill="both")

        # Tab 1
        ttk.Label(tab1, text="Choose a visualiser:").grid(column=0, row=0)
        ttk.Label(tab1, text="Choose a chord style:").grid(column=0, row=1)

        self.style_menu = ttk.Combobox(tab1, values=self.vis_names, state="readonly")
        self.chord_menu = ttk.Combobox(tab1, values=self.chord_styles, state="readonly")

        self.style_menu.set(self.visualisation.name)
        self.chord_menu.set(self.chord_style)
        
        self.style_menu.grid(column=1, row=0)
        self.chord_menu.grid(column=1, row=1)

        # Tab 2 
        ttk.Label(tab2, text="Edge margin proportion").grid(column=0, row=0)
        ttk.Label(tab2, text="Chord margin proportion").grid(column=0, row=1)
        ttk.Label(tab2, text="Pixels to remove between consecutive notes").grid(column=0, row=2)
        ttk.Label(tab2, text="Pixels to remove between simultaneous notes").grid(column=0, row=3)

        self.edge_proportion_input = ttk.Spinbox(tab2, from_=0, to=0.49, increment=0.01, state="readonly")
        self.chord_proportion_input = ttk.Spinbox(tab2, from_=0, to=0.49, increment=0.01, state="readonly")
        self.consecutive_gap_input = ttk.Spinbox(tab2, from_=0, to=10, state="readonly")
        self.simultaneous_gap_input = ttk.Spinbox(tab2, from_=0, to=10, state="readonly")

        self.edge_proportion_input.set(self.edge_proportion)
        self.chord_proportion_input.set(self.chord_proportion)
        self.consecutive_gap_input.set(self.consecutive_gap)
        self.simultaneous_gap_input.set(self.simultaneous_gap)

        self.edge_proportion_input.grid(column=1, row=0)
        self.chord_proportion_input.grid(column=1, row=1)
        self.consecutive_gap_input.grid(column=1, row=2)
        self.simultaneous_gap_input.grid(column=1, row=3)

        # Tab 3
        ttk.Label(tab3, text="Notes Filled In?").grid(column=0, row=0)
        ttk.Label(tab3, text="Draw Margin?").grid(column=0, row=1)
        ttk.Label(tab3, text="Chord Lines Enabled?").grid(column=0, row=2)
        ttk.Label(tab3, text="Time Marker Enabled?").grid(column=0, row=3)
        ttk.Label(tab3, text="Note Shape").grid(column=0, row=4)
        ttk.Label(tab3, text="Chord Side").grid(column=0, row=5)
        ttk.Label(tab3, text="Note Activation Brightness").grid(column=0, row=6)
        ttk.Label(tab3, text="Notes End Offscreen?").grid(column=0, row=7)
        

        self.filled_in_input = ttk.Checkbutton(tab3)
        self.draw_margin_input = ttk.Checkbutton(tab3)
        self.rounded_corners_input = ttk.Combobox(tab3, values=self.rounded_options, state="readonly")
        self.chord_side_input = ttk.Combobox(tab3, values=self.chord_side_options, state="readonly")
        self.chord_lines_input = ttk.Checkbutton(tab3)
        self.time_marker_input = ttk.Checkbutton(tab3)
        self.activation_brightness_input = ttk.Spinbox(tab3, from_=-1, to=1, increment=0.1, state="readonly")
        self.notes_end_input = ttk.Checkbutton(tab3)

        button_state = {True: 'selected', False: '!selected'}
        self.filled_in_input.state([button_state[self.are_notes_filled]])
        self.draw_margin_input.state([button_state[self.should_draw_margin]])
        self.rounded_corners_input.set(self.roundedness)
        self.chord_side_input.set(self.chord_side)
        self.chord_lines_input.state([button_state[self.chord_lines_enabled]])
        self.time_marker_input.state([button_state[self.time_marker_enabled]])
        self.activation_brightness_input.set(self.activation_brightness)
        self.notes_end_input.state([button_state[self.notes_end_offscreen]])
        

        self.filled_in_input.grid(column=1, row=0)
        self.draw_margin_input.grid(column=1, row=1)
        self.chord_lines_input.grid(column=1, row=2)
        self.time_marker_input.grid(column=1, row=3)
        self.rounded_corners_input.grid(column=1, row=4)
        self.chord_side_input.grid(column=1, row=5)
        self.activation_brightness_input.grid(column=1, row=6)
        self.notes_end_input.grid(column=1, row=7)
        

        # Tab 4
        ttk.Label(tab4, text="Frame Rate").grid(column=0, row=0)
        ttk.Label(tab4, text="Seconds Before Start").grid(column=0, row=1)
        ttk.Label(tab4, text="Filename (.mp4)").grid(column=0, row=2)
        
        self.folder_text = ttk.Label(tab4, text=f"Folder To Save In: {self.folder_to_save}")
        self.folder_text.grid(column=0, row=3)
        self.chord_path_text = ttk.Label(tab4, text=f"Path to chords file: {self.chord_path}")
        self.chord_path_text.grid(column=0, row=4)
        
        self.frame_rate_input = ttk.Combobox(tab4, values=self.frame_rates, state="readonly")
        self.seconds_before_input = ttk.Spinbox(tab4, from_=0, to=10, increment=0.1, state="readonly")
        self.file_name_input = ttk.Entry(tab4)
        self.folder_browse_button = ttk.Button(tab4, text="Browse", command=self.prompt_folder_selection)
        self.chord_browse_button = ttk.Button(tab4, text="Browse", command=self.prompt_file_selection)

        # You do not need to set a default for the file browsing, since the only input was a button
        self.frame_rate_input.set(self.frame_rate)
        self.seconds_before_input.set(self.seconds_before_start)
        self.file_name_input.insert(0, self.file_name)

        self.frame_rate_input.grid(column=1, row=0)
        self.seconds_before_input.grid(column=1, row=1)
        self.file_name_input.grid(column=1, row=2)
        self.folder_browse_button.grid(column=1, row=3)
        self.chord_browse_button.grid(column=1, row=4)

        # Tab 5
        """
        Color preview will be a container which gives a preview of the color scheme of the selected theme.
        It will contain the frames 'palette_preview' and 'bg_color_preview'.
        """
        
        ttk.Label(tab5, text="Theme").grid(column=0, row=0)
        self.theme_menu = ttk.Combobox(tab5, values=self.theme_list, state="readonly")

        color_preview = tk.Frame(tab5, height=200) # For showing the color palette
        self.palette_preview = tk.Frame(color_preview, height=200, width=200)
        self.bg_color_preview = tk.Frame(color_preview, height=200, width=200)
        
        refresh_button = ttk.Button(tab5, text="Preview/Reorder", command=lambda: self.reorder_theme())
        shuffle_button = ttk.Button(tab5, text="Shuffle", command=lambda: self.shuffle_theme())
        
        self.theme_menu.set(self.theme.name)
        self.theme_menu.grid(column=1, row=0)

        # Display the color previews
        color_preview.grid(column=0, row=1, columnspan=3, sticky="nsew")
        self.update_color_preview(self.palette_preview, self.bg_color_preview)
        
        refresh_button.grid(column=2, row=0)
        shuffle_button.grid(column=3, row=0)

        # Open the last selected tab since last closing
        self.tab_control.select(self.last_selected_tab)
                           
        # Handle exiting
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.bind('<Escape>', self.closing_from_escape)
        self.root.mainloop()

    def update_color_preview(self, palette_frame, bg_frame):
        """Displays a preview of what the colors for the theme will look like, including the background color."""

        # Remove all colors from the frame first
        self.clear_frame(palette_frame)
        self.clear_frame(bg_frame)
        
        self.theme = THEMES[self.theme_menu.get()]
        
        for color in self.theme.current_colors:
            color_frame = tk.Frame(
                palette_frame,
                width=round(200 / len(self.theme.current_colors)),
                bg=color
            )
            color_frame.pack(fill=tk.BOTH, side=tk.LEFT, expand=True)
            Hovertip(color_frame, color)

        # Update the preview for the background and margin color

        # Render a gradient
        if len(self.theme.bg_color) == 2:

            width = 100
            height = 200
            limit = height
            bg_color = tk.Canvas(bg_frame, width=width, height=height)
            top_color, bottom_color = self.theme.bg_color

            (r1,g1,b1) = convert_hex_to_rgb(top_color)
            (r2,g2,b2) = convert_hex_to_rgb(bottom_color)
            dr = (r2-r1) / limit
            dg = (g2-g1) / limit
            db = (b2-b1) / limit

            for i in range(limit):
                r1,g1,b1 = r1+dr, g1+dg, b1+db
                color = convert_rgb_to_hex(r1, g1, b1)
                bg_color.create_line(0, i, height, i, fill=color)
        
        else:
            bg_color = tk.Frame(bg_frame, width=100, height=200, bg=self.theme.bg_color)
            
        margin_color = tk.Frame(bg_frame, width=100, height=200, bg=self.theme.margin_color)
        bg_color.pack(fill=tk.BOTH, side=tk.LEFT, expand=True)
        margin_color.pack(fill=tk.BOTH, side=tk.LEFT, expand=True)
        
        palette_frame.pack(fill=tk.BOTH, side=tk.LEFT, expand=True)
        bg_frame.pack(fill=tk.BOTH, side=tk.LEFT, expand=True)
        
        Hovertip(bg_color, self.theme.bg_color)
        Hovertip(margin_color, self.theme.margin_color)

    def shuffle_theme(self):
        """This will offset the color palette by a random amount, so that the colors which look nice together stay together."""
        
        colors = self.theme.current_colors

        if len(colors) == 1:
            shift = 0
        else:
            shift = random.randint(1, len(colors)-1)
            
        self.theme.current_colors = colors[shift:] + colors[:shift]
        self.update_color_preview(self.palette_preview, self.bg_color_preview)

    def reorder_theme(self):
        self.theme.current_colors = self.theme.note_colors
        self.update_color_preview(self.palette_preview, self.bg_color_preview)
        
    def clear_frame(self, frame):
        """Removes all widgets in a frame without destroying it first."""

        for widget in frame.winfo_children():
            widget.destroy()
            
    def prompt_folder_selection(self):
        folder = tk.filedialog.askdirectory(
            parent=self.root,
            title="Choose an output file",
        )
        if folder:
            self.folder_to_save = folder
            self.folder_text['text'] = f"Folder To Save In: {self.folder_to_save}"

    def prompt_file_selection(self):            
        """Create a Tk file dialog and cleanup when finished"""

        path = tk.filedialog.askopenfilename(
            parent=self.root,
            title="Select the chord file",
            filetypes=[("Text files", 'txt')]
            )
        
        if path:
            # See if chord path is valid
            try:
                self.chords = get_chords(path)
            except AssertionError:
                tk.messagebox.showerror(title="Invalid File!", message=f"This was not a valid chord path!\nDefaulting to the file: {self.chord_path}")
            else:
                self.chord_path = path
                self.chord_path_text['text'] = f"Path to chords file: {self.chord_path}"
                 
    def closing_from_escape(self, event):
        self.on_closing()
        
    def on_closing(self):
        """Grabs the current values from all options when leaving the options."""

        self.last_selected_tab = self.tab_control.index('current')

        # Tab 1
        self.visualisation = self.style_menu.get()
        self.chord_style = self.chord_menu.get()

        # Tab 2
        self.edge_margin_proportion = float(self.edge_proportion_input.get())
        self.chord_margin_proportion = float(self.chord_proportion_input.get())
        self.pixels_to_remove_between_consecutive_notes = int(self.consecutive_gap_input.get())
        self.pixels_to_remove_between_simultaneous_notes = int(self.simultaneous_gap_input.get())

        # Tab 3
        self.are_notes_filled = 'selected' in self.filled_in_input.state()
        self.should_draw_margin = 'selected' in self.draw_margin_input.state()
        self.roundedness = self.rounded_corners_input.get()
        self.chord_side = self.chord_side_input.get()
        self.chord_lines_enabled = 'selected' in self.chord_lines_input.state()
        self.time_marker_enabled = 'selected' in self.time_marker_input.state()
        self.activation_brightness = float(self.activation_brightness_input.get())
        self.notes_end_offscreen = 'selected' in self.notes_end_input.state()

        # Tab 4
        self.frame_rate = int(self.frame_rate_input.get())
        self.seconds_before_start = float(self.seconds_before_input.get())

        # Tab 5
        self.theme = THEMES[self.theme_menu.get()]

        # See if filename is valid
        file_name = self.file_name_input.get()

        if not self.validate_file_name(file_name):
            tk.messagebox.showerror(title="Invalid Filename!", message=f"You can only use alphanumeric characters and underscores in filenames!\nDefaulting to the file name: {self.file_name}")
        else:
            self.file_name = self.file_name_input.get()    
              
        self.root.destroy()

    @staticmethod
    def validate_file_name(file_name):
        for i in file_name:
            if not (i.isalnum() or i == '_'):
                return False
        return True
        

    def get_configuration(self):
        config = {
            "visualisation": self.visualisation,
            "chord_style": self.chord_style,
            
            "edge_margin_proportion": self.edge_margin_proportion,
            "chord_margin_proportion": self.chord_margin_proportion,
            "pixels_to_remove_between_consecutive_notes": self.pixels_to_remove_between_consecutive_notes,
            "pixels_to_remove_between_simultaneous_notes": self.pixels_to_remove_between_simultaneous_notes,
            
            "are_notes_filled": self.are_notes_filled,
            "roundedness": self.roundedness,
            "should_draw_margin": self.should_draw_margin,
            "chord_side": self.chord_side,
            "chord_lines_enabled": self.chord_lines_enabled,
            "time_marker_enabled": self.time_marker_enabled,
            "activation_brightness": self.activation_brightness,
            "notes_end_offscreen": self.notes_end_offscreen,
            
            "frame_rate": self.frame_rate,
            "seconds_before_start": self.seconds_before_start,            
            "file_name": self.file_name,
            "folder_to_save": self.folder_to_save,
            "chord_path": self.chord_path,

            "last_selected_tab": self.last_selected_tab,

            "theme": self.theme
        }

        """
        for k, v in config.items():
            print(k, v)
        """
        
        return config
    
if __name__ == '__main__':
    
    config = get_config("options.cfg")["DEFAULT"]
    app = Application(config)

    # Default render engine which runs on start up
    app.run()
