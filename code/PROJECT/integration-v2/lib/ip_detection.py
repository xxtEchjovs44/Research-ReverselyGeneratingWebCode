import cv2
import numpy as np

import ip_draw as draw
import ip_preprocessing as pre
import ip_detection_utils as util
import ocr_classify_text as ocr
from CONFIG import Config

C = Config()


def get_corner(boundaries):
    """
    Get the top left and bottom right points of boundary
    :param boundaries: boundary: [top, bottom, left, right]
                        -> up, bottom: (column_index, min/max row border)
                        -> left, right: (row_index, min/max column border) detect range of each row
    :return: corners: [(top_left, bottom_right)]
                        -> top_left: (column_min, row_min)
                        -> bottom_right: (column_max, row_max)
    """
    corners = []
    for boundary in boundaries:
        top_left = (min(boundary[0][0][0], boundary[1][-1][0]), min(boundary[2][0][0], boundary[3][-1][0]))
        bottom_right = (max(boundary[0][0][0], boundary[1][-1][0]), max(boundary[2][0][0], boundary[3][-1][0]))
        corner = (top_left, bottom_right)
        corners.append(corner)
    return corners


def select_corner(corners, compos_class, class_name):
    """
    Select corners in given compo type
    """
    corners_wanted = []
    for i in range(len(compos_class)):
        if compos_class[i] == class_name:
            corners_wanted.append(corners[i])
    return corners_wanted


def merge_corner(corners, compos_class):
    """
    i. merge overlapped corners
    ii. remove nested corners
    :param corners: corners: [(top_left, bottom_right)]
                            -> top_left: (column_min, row_min)
                            -> bottom_right: (column_max, row_max)
    :return: new corners
    """
    def merge_overlapped(corner_a, corner_b):
        (top_left_a, bottom_right_a) = corner_a
        (col_min_a, row_min_a) = top_left_a
        (col_max_a, row_max_a) = bottom_right_a
        (top_left_b, bottom_right_b) = corner_b
        (col_min_b, row_min_b) = top_left_b
        (col_max_b, row_max_b) = bottom_right_b

        col_min = min(col_min_a, col_min_b)
        col_max = max(col_max_a, col_max_b)
        row_min = min(row_min_a, row_min_b)
        row_max = max(row_max_a, row_max_b)
        return (col_min, row_min), (col_max, row_max)

    new_corners = []
    new_class = []
    for i in range(len(corners)):
        corner = corners[i]
        is_intersected = False
        for i in range(len(new_corners)):
            r = util.corner_relation(corner, new_corners[i])
            # if corner is in new_corners[i], ignore corner
            if r == -1:
                is_intersected = True
                break
            # if new_corners[i] is in corner, replace corners[i] with corner
            elif r == 1:
                is_intersected = True
                new_corners[i] = corner
            # if [i] and [j] are overlapped
            if r == 2:
                is_intersected = True
                new_corners[i] = merge_overlapped(corner, new_corners[i])

        if not is_intersected:
            new_corners.append(corner)
            new_class.append(compos_class[i])
    return new_corners, new_class


def strip_img(corners_compo, compos_class, corners_img):
    """
    Separate img from other compos
    :return: compos without img
    """
    corners_compo_withuot_img = []
    compo_class_withuot_img = []
    for i in range(len(compos_class)):
        if compos_class[i] == 'img':
            corners_img.append(corners_compo[i])
        else:
            corners_compo_withuot_img.append(corners_compo[i])
            compo_class_withuot_img.append(compos_class[i])
    return corners_compo_withuot_img, compo_class_withuot_img


def compo_in_img(processing, org, binary, corners_img,
                 corners_block, corners_compo, compos_class,    # output
                 min_compo_edge_length=C.THRESHOLD_UICOMPO_MIN_EDGE_LENGTH):
    """
    Detect potential UI components inner img;
    Only leave non-img
    """
    pad = 2
    for corner in corners_img:
        (top_left, bottom_right) = corner
        (col_min, row_min) = top_left
        (col_max, row_max) = bottom_right
        col_min = max(col_min - pad, 0)
        col_max = min(col_max + pad, org.shape[1])
        row_min = max(row_min - pad, 0)
        row_max = min(row_max + pad, org.shape[0])
        height_img = row_max - row_min
        width_img = col_max - col_min

        # ignore small ones
        if height_img <= min_compo_edge_length or width_img <= min_compo_edge_length:
            continue
            
        clip_org = org[row_min:row_max, col_min:col_max]
        clip_bin = binary[row_min:row_max, col_min:col_max]
        clip_bin = pre.reverse_binary(clip_bin)

        corners_block_new, corners_compo_new, compos_class_new = processing(clip_org, clip_bin, main=False)
        corners_block_new = util.corner_cvt_relative_position(corners_block_new, col_min, row_min)
        corners_compo_new = util.corner_cvt_relative_position(corners_compo_new, col_min, row_min)

        assert len(corners_compo_new) == len(compos_class_new)

        # ignore blocks superposed on its parent img
        for b in corners_block_new:
            (col_min_new, row_min_new), (col_max_new, row_max_new) = b
            height_new = row_max_new - row_min_new
            width_new = col_max_new - col_min_new
            if height_new / height_img < 0.9 and width_new / width_img < 0.9:
                corners_block.append(corners_block_new)

        # only leave non-img elements
        for i in range(len(corners_compo_new)):
            if compos_class_new[i] != 'img':
                # ignore compos superposed on its parent img
                (col_min_new, row_min_new), (col_max_new, row_max_new) = corners_compo_new[i]
                height_new = row_max_new - row_min_new
                width_new = col_max_new - col_min_new
                if height_new / height_img < 0.9 and width_new / width_img < 0.9:
                    corners_compo.append(corners_compo_new[i])
                    compos_class.append(compos_class_new[i])


def block_or_compo(org, binary, corners,
                   max_thickness=C.THRESHOLD_BLOCK_MAX_BORDER_THICKNESS, max_block_cross_points=C.THRESHOLD_BLOCK_MAX_CROSS_POINT,
                   min_block_edge=C.THRESHOLD_BLOCK_MIN_EDGE_LENGTH, max_img_edge_ratio=C.THRESHOLD_IMG_MIN_EDGE_RATION,
                   min_compo_edge=C.THRESHOLD_UICOMPO_MIN_EDGE_LENGTH, max_compo_edge=C.THRESHOLD_UICOMPO_MAX_EDGE_LENGTH,
                   min_img_height=C.THRESHOLD_IMG_MIN_HEIGHT):
    """
    Check if the objects are img components or just block
    :param org: Original image
    :param binary:  Binary image from pre-processing
    :param corners: [(top_left, bottom_right)]
                    -> top_left: (column_min, row_min)
                    -> bottom_right: (column_max, row_max)
    :param max_thickness: The max thickness of border of blocks
    :param max_block_cross_points: Ratio of point of interaction
    :return: corners of blocks and imgs
    """
    blocks = []
    imgs = []
    compos = []
    for corner in corners:
        (top_left, bottom_right) = corner
        (col_min, row_min) = top_left
        (col_max, row_max) = bottom_right
        height = row_max - row_min
        width = col_max - col_min

        # select UI component candidates
        if min_compo_edge < height < max_compo_edge:
            compos.append(corner)
            continue

        block = False
        vacancy = [0, 0, 0, 0]
        for i in range(1, max_thickness):
            try:
                # up down
                if vacancy[0] == 0 and (col_max - col_min - 2 * i) is not 0 and (
                        np.sum(binary[row_min + i, col_min + i: col_max - i]) / 255) / (col_max - col_min - 2 * i) <= max_block_cross_points:
                    vacancy[0] = 1
                # bottom-up
                if vacancy[1] == 0 and (col_max - col_min - 2 * i) is not 0 and (
                        np.sum(binary[row_max - i, col_min + i: col_max - i]) / 255) / (col_max - col_min - 2 * i) <= max_block_cross_points:
                    vacancy[1] = 1
                # left to right
                if vacancy[2] == 0 and (row_max - row_min - 2 * i) is not 0 and (
                        np.sum(binary[row_min + i: row_max - i, col_min + i]) / 255) / (row_max - row_min - 2 * i) <= max_block_cross_points:
                    vacancy[2] = 1
                # right to left
                if vacancy[3] == 0 and (row_max - row_min - 2 * i) is not 0 and (
                        np.sum(binary[row_min + i: row_max - i, col_max - i]) / 255) / (row_max - row_min - 2 * i) <= max_block_cross_points:
                    vacancy[3] = 1
                if np.sum(vacancy) == 4:
                    block = True
            except:
                pass

        # too big to be UI components
        if block:
            if height > min_block_edge and width > min_block_edge:
                blocks.append(corner)
        # filter out small objects
        else:
            if height > min_img_height or width / height < max_img_edge_ratio:
                imgs.append(corner)
    return blocks, imgs, compos


def compo_irregular(org, corners,
                    corners_img, corners_compo,     # output
                    max_img_edge_ratio=C.THRESHOLD_IMG_MIN_EDGE_RATION, min_img_height=C.THRESHOLD_IMG_MIN_HEIGHT,
                    min_compo_edge=C.THRESHOLD_UICOMPO_MIN_EDGE_LENGTH, max_compo_edge=C.THRESHOLD_UICOMPO_MAX_EDGE_LENGTH):
    """
    Select potential irregular shaped elements by checking the height and width
    Check the edge ratio for img components to avoid text misrecognition
    :param org: Original image
    :param corners: [(top_left, bottom_right)]
                    -> top_left: (column_min, row_min)
                    -> bottom_right: (column_max, row_max)
    :param min_compo_edge: ignore small objects
    :return: corners of img
    """
    for corner in corners:
        (top_left, bottom_right) = corner
        (col_min, row_min) = top_left
        (col_max, row_max) = bottom_right
        height = row_max - row_min
        width = col_max - col_min

        # select UI component candidates
        if min_compo_edge < height < max_compo_edge:
            corners_compo.append(corner)
        elif height > min_img_height or width / height < max_img_edge_ratio:
            corners_img.append(corner)


def compo_filter(org, corners, compos_class,
                 max_compo_egde=C.THRESHOLD_UICOMPO_MAX_EDGE_LENGTH, max_icon_edge=C.THRESHOLD_ICON_MAX_EDGE):
    """
    Filter compos and imgs according to edge length
    :param org: Original image
    :param corners: [(top_left, bottom_right)]
                    -> top_left: (column_min, row_min)
                    -> bottom_right: (column_max, row_max)
    :return: corners of left components, classes of them
    """
    corners_compo_new = []
    compos_class_new = []
    for i in range(len(corners)):
        compo = compos_class[i]
        corner = corners[i]
        (top_left, bottom_right) = corner
        (col_min, row_min) = top_left
        (col_max, row_max) = bottom_right
        height = row_max - row_min
        width = col_max - col_min

        if height < max_icon_edge and width < max_icon_edge:
            compo = 'icon'
        elif compo != 'img':
            # too big to be UI components
            if height > max_compo_egde:
                continue
        corners_compo_new.append(corner)
        compos_class_new.append(compo)

        # print("Height:%d, Width:%d, Area:%d, Perimeter:%d" % (height, width, height*width, height*2+width*2))
        # draw.draw_bounding_box(org, corners_compo_new, show=True)

    return corners_compo_new, compos_class_new


def img_shrink(org, binary, corners,
               min_line_length_h=C.THRESHOLD_LINE_MIN_LENGTH_H, min_line_length_v=C.THRESHOLD_LINE_MIN_LENGTH_V,
               max_thickness=C.THRESHOLD_LINE_THICKNESS):
    """
    For imgs that are part of a block, strip the img
    """

    corners_shrunken = []
    pad = 2
    for corner in corners:
        (top_left, bottom_right) = corner
        (col_min, row_min) = top_left
        (col_max, row_max) = bottom_right

        col_min = max(col_min - pad, 0)
        col_max = min(col_max + pad, org.shape[1])
        row_min = max(row_min - pad, 0)
        row_max = min(row_max + pad, org.shape[0])

        clip_bin = binary[row_min:row_max, col_min:col_max]
        clip_org = org[row_min:row_max, col_min:col_max]

        # detect lines in the image
        lines_h, lines_v = line_detection(clip_bin, min_line_length_h, min_line_length_v, max_thickness)
        # select those perpendicularly intersect with others at endpoints
        lines_h, lines_v = util.line_check_perpendicular(lines_h, lines_v, max_thickness)
        # convert the position of lines into relative position in the entire image
        lines_h, lines_v = util.line_cvt_relative_position(col_min, row_min, lines_h, lines_v)

        # shrink corner according to the lines
        corner_shrunken = util.line_shrink_corners(corner, lines_h, lines_v)
        corners_shrunken.append(corner_shrunken)

    return corners_shrunken


# remove imgs that contain text
def rm_text(org, corners, compo_class,
            max_text_height=C.THRESHOLD_TEXT_MAX_HEIGHT, max_text_width=C.THRESHOLD_TEXT_MAX_WIDTH,
            
            ocr_padding=C.OCR_PADDING, ocr_min_word_area=C.OCR_MIN_WORD_AREA, show=False):
    """
    Remove area that full of text
    :param org: original image
    :param corners: [(top_left, bottom_right)]
                    -> top_left: (column_min, row_min)
                    -> bottom_right: (column_max, row_max)
    :param compo_class: classes of corners
    :param max_text_height: Too large to be text
    :param max_text_width: Too large to be text
    :param ocr_padding: Padding for clipping
    :param ocr_min_word_area: If too text area ratio is too large
    :param show: Show or not
    :return: corners without text objects
    """
    new_corners = []
    new_class = []
    for i in range(len(corners)):
        corner = corners[i]
        (top_left, bottom_right) = corner
        (col_min, row_min) = top_left
        (col_max, row_max) = bottom_right
        height = row_max - row_min
        width = col_max - col_min
        # highly likely to be block or img if too large
        if height > max_text_height and width > max_text_width:
            new_corners.append(corner)
        else:
            row_min = row_min - ocr_padding if row_min - ocr_padding >= 0 else 0
            row_max = row_max + ocr_padding if row_max + ocr_padding < org.shape[0] else org.shape[0]
            col_min = col_min - ocr_padding if col_min - ocr_padding >= 0 else 0
            col_max = col_max + ocr_padding if col_max + ocr_padding < org.shape[1] else org.shape[1]
            # check if this area is text
            clip = org[row_min: row_max, col_min: col_max]
            if not ocr.is_text(clip, ocr_min_word_area, show=show):
                new_corners.append(corner)
                new_class.append(compo_class[i])
    return new_corners, new_class


def line_detection(binary,
                   min_line_length_h=C.THRESHOLD_LINE_MIN_LENGTH_H, min_line_length_v=C.THRESHOLD_LINE_MIN_LENGTH_V,
                   max_thickness=C.THRESHOLD_LINE_THICKNESS):
    """
    Detect lines
    :param binary: Binary image from pre-processing
    :param min_line_length_h: Min length for horizontal lines
    :param min_line_length_v: Min length for vertical lines
    :param max_thickness
    :return: lines: [line_h, line_v]
            -> line_h: horizontal {'head':(column_min, row), 'end':(column_max, row), 'thickness':int)
            -> line_v: vertical {'head':(column, row_min), 'end':(column, row_max), 'thickness':int}
    """
    def no_neighbor(start_row, start_col, mode, line=None):
        """
        check this point has adjacent points in orthogonal direction
        """
        if mode == 'h':
            for t in range(max_thickness + 1):
                if start_row + t >= binary.shape[0] or binary[start_row + t, start_col] == 0:
                    # if not start point, update the thickness of this line
                    if line is not None:
                        line['thickness'] = max(line['thickness'], t)
                    return True
                mark_h[start_row + t, start_col] = 255
            return False
        elif mode == 'v':
            for t in range(max_thickness + 1):
                if start_col + t >= binary.shape[1] or binary[start_row, start_col + t] == 0:
                    # if not start point, update the thickness of this line
                    if line is not None:
                        line['thickness'] = max(line['thickness'], t)
                    return True
                mark_v[start_row, start_col + t] = 255
            return False

    row, column = binary.shape[0], binary.shape[1]
    mark_h = np.zeros(binary.shape, dtype=np.uint8)
    mark_v = np.zeros(binary.shape, dtype=np.uint8)
    lines_h = []
    lines_v = []
    x, y = 0, 0
    while x < row - 1 or y < column - 1:
        # horizontal
        new_line = False
        head, end = None, None
        line = {}
        for j in range(column):
            # line start
            if not new_line and mark_h[x][j] == 0 and binary[x][j] > 0 and no_neighbor(x, j, 'h'):
                head = j
                new_line = True
                line['head'] = [head, x]
                line['thickness'] = -1
            # line end
            elif new_line and (j == column - 1 or mark_h[x][j] > 0 or binary[x][j] == 0 or not no_neighbor(x, j, 'h', line)):
                end = j
                new_line = False
                if end - head > min_line_length_h:
                    line['end'] = [end, x]
                    lines_h.append(line)
                line = {}

        # vertical
        new_line = False
        head, end = None, None
        line = {}
        for i in range(row):
            # line start
            if not new_line and mark_v[i][y] == 0 and binary[i][y] > 0 and no_neighbor(i, y, 'v'):
                head = i
                new_line = True
                line['head'] = [y, head]
                line['thickness'] = 0
            # line end
            elif new_line and (i == row - 1 or mark_v[i][y] > 0 or binary[i][y] == 0 or not no_neighbor(i, y, 'v', line)):
                end = i
                new_line = False
                if end - head > min_line_length_v:
                    line['end'] = [y, end]
                    lines_v.append(line)
                line = {}

        if x < row - 1:
            x += 1
        if y < column - 1:
            y += 1

    return lines_h, lines_v


# take the binary image as input
# calculate the connected regions -> get the bounding boundaries of them -> check if those regions are rectangles
# return all boundaries and boundaries of rectangles
def boundary_detection(binary,
                       min_obj_area=C.THRESHOLD_OBJ_MIN_AREA, min_obj_perimeter=C.THRESHOLD_OBJ_MIN_PERIMETER,
                       line_thickness=C.THRESHOLD_LINE_THICKNESS, min_rec_evenness=C.THRESHOLD_REC_MIN_EVENNESS,
                       max_dent_ratio=C.THRESHOLD_REC_MAX_DENT_RATIO):
    """
    :param binary: Binary image from pre-processing
    :param min_obj_area: If not pass then ignore the small object
    :param min_obj_perimeter: If not pass then ignore the small object
    :param line_thickness: If not pass then ignore the slim object
    :param min_rec_evenness: If not pass then this object cannot be rectangular
    :param max_dent_ratio: If not pass then this object cannot be rectangular
    :return: boundary: [top, bottom, left, right]
                        -> up, bottom: (column_index, min/max row border)
                        -> left, right: (row_index, min/max column border) detect range of each row
    """
    mark = np.full(binary.shape, 0, dtype=np.uint8)
    boundary_rec = []
    boundary_nonrec = []
    row, column = binary.shape[0], binary.shape[1]

    for i in range(row):
        for j in range(column):
            if binary[i, j] == 255 and mark[i, j] == 0:
                # get connected area
                area = util.boundary_bfs_connected_area(binary, i, j, mark)
                # ignore small area
                if len(area) < min_obj_area:
                    continue

                # calculate the boundary of the connected area
                boundary = util.boundary_get_boundary(area)
                # ignore small area
                perimeter = np.sum([len(b) for b in boundary])
                if perimeter < min_obj_perimeter:
                    continue

                # check if it is line by checking the length of edges
                if util.boundary_is_line(boundary, line_thickness):
                    continue

                # rectangle check
                if util.boundary_is_rectangle(boundary, min_rec_evenness, max_dent_ratio):
                    boundary_rec.append(boundary)
                else:
                    boundary_nonrec.append(boundary)
    return boundary_rec, boundary_nonrec
