import cv2
import numpy as np
import os
import pandas as pd

import img_drawLabel as draw


# extent labels that excess the segment size to the next segment
def segment_extent(item, index, segment_label, segment_size):
    # calculate the extent segment
    extent_item = item.copy()
    extent_item['by'] = 0
    extent_item['bh'] = item['bh'] - (segment_size - item['by'] - 1)
    extent_item['segment_no'] = item['segment_no'] + 1

    # revise the org large segment
    item['bh'] = segment_size - item['by'] - 1

    # append the new items
    segment_label.loc[index] = item

    # extent recursively until the size is smaller than the segment size
    if (extent_item['by'] + extent_item['bh']) >= segment_size:
        index = extent_item(extent_item, index + 1, segment_label, segment_size)
    else:
        index += 1
        segment_label.loc[index] = extent_item

    return index


# draw label on the segment images
def segment_draw(segment_org_path, labeled_img_path, label_path, show=True):
    label = pd.read_csv(label_path)

    if len(label) == 0:
        print("No component needs to be labeled \n")
        return

    for s in range(label.iloc[-1].segment_no + 1):
        seg_input_path = os.path.join(segment_org_path, str(s) + '.png')
        seg_output_path = os.path.join(labeled_img_path, str(s) + '.png')
        seg_img = cv2.imread(seg_input_path)
        seg_label = label[label['segment_no'] == s]
        draw.label(seg_label, seg_img, seg_output_path, show)
    print('Labeled img saved in ' + labeled_img_path + '\n')


# change the coordinates and size of labels to fit the img segment
def segment_label(label_path, segment_size=600):
    # read the original label
    org_label = pd.read_csv(label_path, index_col=0)

    # initialize the segment labels by adding segment_no column and changing the relative label coordinate
    colums = org_label.columns.values
    colums = np.append(colums, ['segment_no'])
    segment_label = pd.DataFrame(columns=colums)

    index = 0
    for i in range(len(org_label)):
        item = org_label.iloc[i].copy()
        segment_no = int(item['by'] / segment_size)
        item['by'] = item['by'] % segment_size
        item['segment_no'] = segment_no
        # for those excess the segment size range
        if (item['by'] + item['bh']) >= segment_size:
            index = segment_extent(item, index, segment_label, segment_size)
        else:
            segment_label.loc[index] = item

        index += 1

    segment_label.to_csv(label_path)


# cut the original img into fixed-size segment img
def segment_img(org_img_path, output_segment_path, segment_size=600, show=True):
    img = cv2.imread(org_img_path)
    height_bottom = np.shape(img)[0]

    h = 0
    segment_no = 0
    while h < height_bottom:
        segment_range = {}
        segment_range['top'] = h
        segment_range['bottom'] = h + segment_size if h + segment_size <= height_bottom else height_bottom
        segment_img = img[segment_range['top']:segment_range['bottom'], :, :]
        cv2.imwrite(os.path.join(output_segment_path, str(segment_no) + '.png'), segment_img)

        h += segment_size
        segment_no += 1

        if show:
            cv2.imshow('img', segment_img)
            cv2.waitKey(0)
