import argparse
import os
from math import sqrt, ceil
from multiprocessing import Pool
from os.path import join, dirname

import cv2
import matplotlib.colors as mpl_colors
import numpy as np
from matplotlib import pyplot as plt

from pubgis.pubgis_color import Color, ColorSpace, ColorScaling
from pubgis.template_match_result import MatchResult

MAP_FILE = join(dirname(__file__), "images", "full_map_scaled.jpg")
INDICATOR_MASK_FILE = join(dirname(__file__), "images", "player_indicator_mask.jpg")
INDICATOR_AREA_MASK_FILE = join(dirname(__file__), "images", "player_indicator_area_mask.jpg")
DEFAULT_OUTPUT_FILE = "{}_path.jpg"

DEFAULT_STEP_INTERVAL = 1  # seconds

CROP_BORDER = 30

MAX_SPEED = 130  # km/h, motorcycle
PIXELS_PER_100M = 64
PIXELS_PER_KM = PIXELS_PER_100M * 10
MAX_PIXELS_PER_H = MAX_SPEED * PIXELS_PER_KM
MAX_PIXELS_PER_SEC = MAX_PIXELS_PER_H / 3600

# calibrated based on test cases
COLOR_DIFF_THRESH_1 = 70
TEMPLATE_MATCH_THRESH_1 = .40
COLOR_DIFF_THRESH_2 = 30
TEMPLATE_MATCH_THRESH_2 = .75

PATH_WIDTH = 4

MIN_PROGRESS_MAP_SIZE = 600

DEFAULT_FONT = cv2.FONT_HERSHEY_SIMPLEX
DEBUG_FONT_SIZE_BIG = 0.6
DEBUG_FONT_SIZE_SMALL = 0.3

NO_MATCH_COLOR = Color(mpl_colors.to_rgb("Red"))
MATCH_COLOR = Color(mpl_colors.to_rgb("Lime"))
WHITE = Color(mpl_colors.to_rgb("White"))

DEFAULT_PATH_COLOR = Color(mpl_colors.to_rgb("Lime"), alpha=0.7)

MINIMAP_WIDTH = 252
MINIMAP_HEIGHT = 252
MINIMAP_Y = 798
MINIMAP_X = 1630


# when indexing an image the format is image[y,x]
# but coords are passed as (x,y)


class PUBGISMatch:  # pylint: disable=too-many-instance-attributes
    def __init__(self,
                 video_file,
                 landing_time=0,
                 step_interval=DEFAULT_STEP_INTERVAL,
                 death_time=None,
                 output_file=None,
                 path_color=DEFAULT_PATH_COLOR,
                 debug=False,
                 **_):
        self.video_file = video_file
        self.full_map = cv2.imread(MAP_FILE)
        self.preview_map = np.copy(self.full_map)
        self.gray_full_map = cv2.cvtColor(self.full_map, cv2.COLOR_BGR2GRAY)

        self.landing_time = landing_time
        self.step_interval = step_interval
        self.death_time = death_time

        _, self.indicator_mask = cv2.threshold(cv2.imread(INDICATOR_MASK_FILE, 0),
                                               10,
                                               255,
                                               cv2.THRESH_BINARY)
        _, self.indicator_area_mask = cv2.threshold(cv2.imread(INDICATOR_AREA_MASK_FILE, 0),
                                                    10,
                                                    255,
                                                    cv2.THRESH_BINARY)

        self.debug = debug

        # TODO: double check output file handling.
        self.output_file = output_file

        self.path_color = path_color
        self.all_coords = []

    @staticmethod
    def markup_minimap_debug(minimap, match_found, ind_color, ind_area_color, color_diff, match_val):
        """

        :param minimap:
        :param ind_color:
        :param ind_area_color:
        :param color_diff:
        :param match_val:
        :return:
        """
        ind_rect_corner = (200, 200)
        ind_rect_area_corner = (120, 200)
        rect_size = 50
        text_inset = (8, 15)
        test_spacing = 15

        cv2.putText(minimap, f"{int(color_diff)}", (25, 25), DEFAULT_FONT, DEBUG_FONT_SIZE_BIG, WHITE.get())
        cv2.putText(minimap, f"{match_val:.2f}", (25, 60), DEFAULT_FONT, DEBUG_FONT_SIZE_BIG, WHITE.get())

        cv2.rectangle(minimap,
                      ind_rect_corner,
                      tuple(c + rect_size for c in ind_rect_corner),
                      ind_color.get(),
                      thickness=-1)

        for i, color in enumerate(ind_color.get()):
            corner_x = ind_rect_corner[0] + text_inset[0]
            corner_y = ind_rect_corner[1] + text_inset[1] + i * test_spacing
            cv2.putText(minimap,
                        f'{color}',
                        (corner_x, corner_y),
                        DEFAULT_FONT,
                        DEBUG_FONT_SIZE_SMALL,
                        (0, 0, 0))

        cv2.rectangle(minimap,
                      ind_rect_area_corner,
                      tuple(c + rect_size for c in ind_rect_area_corner),
                      ind_area_color.get(),
                      thickness=-1)

        for i, color in enumerate(ind_area_color.get()):
            corner_x = ind_rect_area_corner[0] + text_inset[0]
            corner_y = ind_rect_area_corner[1] + text_inset[1] + i * test_spacing
            cv2.putText(minimap,
                        f'{color}',
                        (corner_x, corner_y),
                        DEFAULT_FONT,
                        DEBUG_FONT_SIZE_SMALL,
                        (0, 0, 0))

        cv2.rectangle(minimap,
                      (0, 0),
                      (252, 252),
                      MATCH_COLOR.get() if match_found == MatchResult.SUCCESFUL else NO_MATCH_COLOR.get(),
                      thickness=4)

        return minimap

    def template_match(self, percent_minimap):
        """
        Attempt to match the supplied minimap to a section of the larger full map.

        The actual template matching is done by opencv, but there is additional checking that is
        done to ensure that the supplied minimap is actually

        :param percent_minimap:
        :return:
        """
        this_percent, minimap = percent_minimap

        gray_minimap = cv2.cvtColor(minimap, cv2.COLOR_RGB2GRAY)
        height, width = gray_minimap.shape

        _, match_val, _, (min_x, min_y) = cv2.minMaxLoc(cv2.matchTemplate(self.gray_full_map,
                                                                          gray_minimap,
                                                                          cv2.TM_CCOEFF_NORMED))

        ind_color = Color(cv2.mean(minimap, self.indicator_mask)[:3],
                          scaling=ColorScaling.UINT8,
                          space=ColorSpace.BGR)
        ind_area_color = Color(cv2.mean(minimap, self.indicator_area_mask)[:3],
                               scaling=ColorScaling.UINT8,
                               space=ColorSpace.BGR)
        color_diff = sqrt(sum([(c1 - c2) ** 2 for c1, c2 in zip(ind_color.get(),
                                                                ind_area_color.get())]))

        if (color_diff > COLOR_DIFF_THRESH_1 and match_val > TEMPLATE_MATCH_THRESH_1) or \
                (color_diff > COLOR_DIFF_THRESH_2 and match_val > TEMPLATE_MATCH_THRESH_2):
            match_found = MatchResult.SUCCESFUL
        else:
            match_found = MatchResult.OUT_OF_RANGE

        if self.debug:
            cv2.imshow("debug", np.concatenate((self.markup_minimap_debug(minimap,
                                                                          match_found,
                                                                          ind_color,
                                                                          ind_area_color,
                                                                          color_diff,
                                                                          match_val),
                                                self.full_map[min_y:min_y + height,
                                                              min_x:min_x + width]),
                                               axis=1))
            cv2.waitKey(10)

        return match_found, (min_x + width // 2, min_y + height // 2), ind_color, color_diff, \
               match_val, this_percent

    def find_path_bounds(self):
        """
        This function aims to provide bounds for the current path for pleasant viewing.

        To achieve this goal, the bounds provided should be:
            - square to prevent distortion, as the preview box will be square
            - not smaller than the provided minimum size to prevent too much zoom
            - equally padded from the boundaries of the path (in the x and y directions)

        :return: (x, y, w, h)
        """
        if self.all_coords:
            x_list, y_list = zip(*self.all_coords)

            min_x = min(x_list) - CROP_BORDER
            max_x = max(x_list) + CROP_BORDER
            min_y = min(y_list) - CROP_BORDER
            max_y = max(y_list) + CROP_BORDER

            # To make padding easier, round up the path widths to an even number
            # This mean we won't have to pad 1 side with an extra pixel
            x_path_width = int(ceil((max_x - min_x) / 2) * 2)
            y_path_width = int(ceil((max_y - min_y) / 2) * 2)

            output_size = max(MIN_PROGRESS_MAP_SIZE, x_path_width, y_path_width)

            # Allocation the extra space needed to fill up the required size equally on both sides
            x_pad = (output_size - x_path_width) // 2
            y_pad = (output_size - y_path_width) // 2

            x_corner = max(0, min_x - x_pad)
            y_corner = max(0, min_y - y_pad)

            return x_corner, y_corner, output_size, output_size

        return (0, 0) + tuple(self.gray_full_map.shape)

    def process_match(self):
        """

        :return:
        """
        pool = Pool(4)

        for match_found, coords, _, _, _, this_percent in pool.imap(self.template_match,
                                                                    self.video_iterator()):
            if match_found == MatchResult.SUCCESFUL:
                try:
                    cv2.line(self.preview_map,
                             self.all_coords[-1],
                             coords,
                             color=self.path_color.get(),
                             thickness=PATH_WIDTH,
                             lineType=cv2.LINE_AA)
                except IndexError:
                    pass

                self.all_coords.append(coords)

                min_x, min_y, width, height = self.find_path_bounds()
                yield this_percent, self.preview_map[min_y:min_y + height, min_x:min_x + width]

    def video_iterator(self):
        """
        Return the minimap every time_interval seconds from the supplied video, skipping the first start_delay frames.

        :return: iterator that yields (percent, minimap) tuples
        """
        cap = cv2.VideoCapture(self.video_file)
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        landing_frame = int(self.landing_time * fps)
        step_frames = max(int(self.step_interval * fps), 1)
        # TODO: assert death time > landing_time
        if self.death_time is None:
            death_frame = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        else:
            death_frame = int(self.death_time * fps)
        frames_processed = 0
        frames_to_process = death_frame - landing_frame
        initialized = False

        grabbed = True

        for _ in range(landing_frame):
            grabbed = cap.grab()

        while grabbed and frames_processed <= frames_to_process:
            if initialized:
                for _ in range(step_frames - 1):
                    cap.grab()
                frames_processed += step_frames - 1
            else:
                initialized = True

            grabbed, frame = cap.read()
            frames_processed += 1

            if grabbed:
                if frame.shape == (1080, 1920, 3):
                    minimap = frame[MINIMAP_Y:MINIMAP_Y + MINIMAP_HEIGHT,
                                    MINIMAP_X:MINIMAP_X + MINIMAP_WIDTH]
                else:
                    raise ValueError

                percent_processed = min(int((frames_processed / frames_to_process) * 100), 100)
                yield percent_processed, minimap

    def create_output(self):
        """

        :return:
        """
        if self.output_file:
            fig, output_axis = plt.subplots(figsize=(20, 20))
            fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
            output_axis.axes.xaxis.set_visible(False)
            output_axis.axes.yaxis.set_visible(False)
            output_axis.imshow(cv2.cvtColor(self.full_map, cv2.COLOR_BGR2RGB))
            min_x, min_y, width, height = self.find_path_bounds()
            output_axis.axes.set_xlim(min_x, min_x + width)
            output_axis.axes.set_ylim(min_y + height, min_y)

            mpl_color = self.path_color.get_with_alpha(space=ColorSpace.RGB,
                                                       scaling=ColorScaling.PERC)
            output_axis.plot(*zip(*self.all_coords), color=mpl_color, linewidth=PATH_WIDTH)
            fig.savefig(self.output_file)


class ColorAction(argparse.Action):
    """
    This class converts a supplied color string into a Color instance for use
    within the code.
    """

    def __call__(self, parser_arg, namespace, values, option_string=None):
        setattr(namespace, self.dest, Color(mpl_colors.to_rgb(values)))


if __name__ == "__main__":
    PARSER = argparse.ArgumentParser(argument_default=argparse.SUPPRESS)
    PARSER.add_argument('--video_file', required=True)
    PARSER.add_argument('--death_time', type=int)
    PARSER.add_argument('--landing_time', type=int)
    PARSER.add_argument('--step_interval', type=int)
    PARSER.add_argument('--output_file', type=str)
    PARSER.add_argument('--path_color', type=str, action=ColorAction)
    PARSER.add_argument('--debug', action='store_true')
    MATCH = PUBGISMatch(**vars(PARSER.parse_args()))

    for _, progress_map in MATCH.process_match():
        cv2.imshow("progress", progress_map)
        cv2.waitKey(10)

    MATCH.create_output()
