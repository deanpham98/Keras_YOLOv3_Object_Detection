import pdb

import numpy as np
import random
import threading
import warnings
from copy import deepcopy
from keras import backend as K

from .utils.image import (
    TransformParameters,
    adjust_transform_for_image,
    apply_transform,
    resize_image,
)
from .utils.transform import transform_aabb
from ..utils.visualize import draw

class Generator(object):
    def __init__(
        self,
        transform_generator = None,
        enhance_generator = None,
        batch_size=1,
        group_method='random',  # one of 'none', 'random', 'ratio'
        shuffle_groups=True,
        input_shape=(416, 416),
        transform_parameters=None,
        anchors=np.array(((10,13), (16,30), (33,23), (30,61),
    (62,45), (59,119), (116,90), (156,198), (373,326))),
        training=True,
        visualize=False
    ):
        self.transform_generator    = transform_generator
        self.enhance_generator      = enhance_generator
        self.batch_size             = int(batch_size)
        self.group_method           = group_method
        self.shuffle_groups         = shuffle_groups
        self.input_shape            = input_shape
        self.transform_parameters   = transform_parameters or TransformParameters()
        self.anchors                = anchors
        self.group_index            = 0
        self.lock                   = threading.Lock()
        self.training               = training
        self.visualize              = visualize

        if self.training == False:
            self.group_method='none'
            self.shuffle_groups = False
            self.trainsform_generator = None
            self.enhance_generator = None
            self.batch_size = 1
        self.group_images()
        self.classes = {i: self.label_to_name(i) for i in range(self.num_classes())}

    def size(self):
        raise NotImplementedError('size method not implemented')

    def num_classes(self):
        raise NotImplementedError('num_classes method not implemented')

    def name_to_label(self, name):
        raise NotImplementedError('name_to_label method not implemented')

    def label_to_name(self, label):
        raise NotImplementedError('label_to_name method not implemented')

    def image_aspect_ratio(self, image_index):
        raise NotImplementedError('image_aspect_ratio method not implemented')

    def load_image(self, image_index):
        raise NotImplementedError('load_image method not implemented')

    def load_annotations(self, image_index):
        raise NotImplementedError('load_annotations method not implemented')

    def load_annotations_group(self, group):
        return [self.load_annotations(image_index) for image_index in group]

    def filter_annotations(self, image_group, annotations_group, group):
        # test all annotations
        for index, (image, annotations) in enumerate(zip(image_group, annotations_group)):
            assert(isinstance(annotations, np.ndarray)), '\'load_annotations\' should return a list of numpy arrays, received: {}'.format(type(annotations))

            # test x2 < x1 | y2 < y1 | x1 < 0 | y1 < 0 | x2 <= 0 | y2 <= 0 | x2 >= image.shape[1] | y2 >= image.shape[0]
            invalid_indices = np.where(
                (annotations[:, 2] <= annotations[:, 0]) |
                (annotations[:, 3] <= annotations[:, 1]) |
                (annotations[:, 0] < 0) |
                (annotations[:, 1] < 0) |
                (annotations[:, 2] > image.shape[1]) |
                (annotations[:, 3] > image.shape[0])
            )[0]

            # delete invalid indices
            if len(invalid_indices):
                warnings.warn('Image with id {} (shape {}) contains the following invalid boxes: {}.'.format(
                    group[index],
                    image.shape,
                    [annotations[invalid_index, :] for invalid_index in invalid_indices]
                ))
                annotations_group[index] = np.delete(annotations, invalid_indices, axis=0)

        return image_group, annotations_group

    def load_image_group(self, group):
        return [self.load_image(image_index) for image_index in group]

    def random_transform_group_entry(self, image, annotations):
        # randomly transform both image and annotations
        if self.transform_generator and self.training:
            transform = adjust_transform_for_image(next(self.transform_generator), image, self.transform_parameters.relative_translation)
            transform_image     = apply_transform(transform, image, self.transform_parameters)

            # Transform the bounding boxes in the annotations.
            transform_annotations = annotations.copy()
            for index in range(transform_annotations.shape[0]):
                transform_annotations[index, :4] = transform_aabb(transform, transform_annotations[index, :4])
            x = [True, False, True, False, False]
            y = [False, True, False, True, False]

            transform_annotations[:, x] = np.clip(transform_annotations[:, x], 0, transform_image.shape[1])
            transform_annotations[:, y] = np.clip(transform_annotations[:, y], 0, transform_image.shape[0])

            center = (transform_annotations[:, 0:2] + transform_annotations[:, 2:4]) // 2
            annotations_mask = (center[:, 0] > 0) * (center[:, 0] < transform_image.shape[1]) * (center[:, 1] > 0) * (center[:, 1] < transform_image.shape[0])
            transform_annotations = transform_annotations[annotations_mask, :]
            return transform_image, transform_annotations

        return image, annotations

    def random_enhance_group_entry(self, image):
        # randomly transform both image and annotations
        if self.enhance_generator and self.training:
            enhanced_image = self.enhance_generator.random_enhance(image)
            return enhanced_image
            # Transform the bounding boxes in the annotations
        return image

    def resize_image(self, image, annotations, input_shape):
        return resize_image(image, annotations, input_shape=self.input_shape)

    def preprocess_group_entry(self, image, annotations):

        transform_image, transform_annotations = self.random_transform_group_entry(image, annotations)

        resized_image, resized_annotations = self.resize_image(transform_image, transform_annotations.copy(), self.input_shape)

        enhanced_image = self.random_enhance_group_entry(resized_image)

        if self.visualize:
               annots = [np.concatenate((a[:, 0:4], np.ones_like(a[:, 4:5]), a[:, 4:5]), axis=-1) for a in [annotations, transform_annotations, resized_annotations]]
               data = {
		   'original': [image, annots[0]],
		   'transform': [transform_image, annots[1]],
		   'resized': [resized_image, annots[2]],
		   'enhanced': [enhanced_image, annots[2]]
		}
               draw(
		  data    = data,
		  classes = self.classes
                )

        return enhanced_image, resized_annotations

    def preprocess_group(self, image_group, annotations_group):
        for index, (image, annotations) in enumerate(zip(image_group, annotations_group)):
            # preprocess a single group entry
            image, annotations = self.preprocess_group_entry(image, annotations)

            # copy processed data back to group
            image_group[index]       = image
            annotations_group[index] = annotations

        return image_group, annotations_group

    def group_images(self):
        # determine the order of the images
        order = list(range(self.size()))

        if self.group_method == 'random':
            random.shuffle(order)
        elif self.group_method == 'ratio':
            order.sort(key=lambda x: self.image_aspect_ratio(x))

        # divide into groups, one group = one batch
        self.groups = [[order[x % len(order)] for x in range(i, i + self.batch_size)] for i in range(0, len(order), self.batch_size)] \
                      if self.training \
                      else [[order[x] for x in range(i, i + self.batch_size)] for i in range(0, self.batch_size * (self.size() // self.batch_size), self.batch_size)]

    def compute_y_true(self, true_boxes):
            if self.training == False:
                computed_true_boxes = []
                for boxes in true_boxes:
                    boxes_xy = (boxes[:, 0:2] + boxes[:, 2:4]) // 2
                    boxes_wh = boxes[:, 2:4] - boxes[:, 0:2]
                    boxes[:, 0:2] = boxes_xy
                    boxes[:, 2:4] = boxes_wh
                    computed_true_boxes.append(boxes)
                return computed_true_boxes
            anchor_mask = [[6,7,8], [3,4,5], [0,1,2]]

            true_boxes = np.array([box.tolist() + np.zeros((100 - len(box), 5)).tolist() for box in true_boxes], dtype='float32')
            #true_boxes = [np.concatenate((boxes, np.zeros(shape=(100 - len(boxes), 5), dtype=boxes.dtype)), axis=0) for boxes in true_boxes]

            input_shape = np.array(self.input_shape, dtype='int32')

            boxes_xy = (true_boxes[..., 0:2] + true_boxes[..., 2:4]) // 2
            boxes_wh = true_boxes[..., 2:4] - true_boxes[..., 0:2]

            true_boxes[..., 0:2] = boxes_xy / input_shape[::-1]
            true_boxes[..., 2:4] = boxes_wh / input_shape[::-1]

            num_images = true_boxes.shape[0]

            grid_shapes = [input_shape // {0:32, 1:16, 2:8}[l] for l in range(3)]

            y_true = [np.zeros((num_images, grid_shapes[l][0], grid_shapes[l][1], len(anchor_mask[l]), \
	                        5 + self.num_classes()), dtype='float32') for l in range(3)]

            anchors = np.expand_dims(self.anchors, 0)
            anchor_maxes = anchors / 2.
            anchor_mins = -anchor_maxes

            valid_mask = boxes_wh[..., 0] > 0

            for image_index in range(num_images):

	            # Discard zero rows.
                wh = boxes_wh[image_index, valid_mask[image_index]]
                wh = np.expand_dims(wh, -2)

	            # Find bbox max and min coordinates
                box_maxes = wh / 2.
                box_mins = -box_maxes

	            # Find intersection region width and height
                intersect_mins = np.maximum(box_mins, anchor_mins)
                intersect_maxes = np.minimum(box_maxes, anchor_maxes)
                intersect_wh = np.maximum(intersect_maxes - intersect_mins, 0.)

	            # Areas of intersection of (bbox), (anchor), (bbox and anchor)
                intersect_area = intersect_wh[..., 0] * intersect_wh[..., 1]
                box_area = wh[..., 0] * wh[..., 1]
                anchor_area = anchors[..., 0] * anchors[..., 1]

	            # IOU of bboxes and anchors
                iou = intersect_area / (box_area + anchor_area - intersect_area)

	            # Find best anchor for each true box
                best_anchor = np.argmax(iou, axis=-1)

                for box_index, anchor_index in enumerate(best_anchor):
                    for detection_layer in range(3):

	            	    # Check anchor_index to see it belongs to which detection layer
                        if anchor_index in anchor_mask[detection_layer]:

                		  # x, y coordinates of grid cell that the ground truth lies within
                            cell_y = np.floor(true_boxes[image_index, box_index, 0] * grid_shapes[detection_layer][1]).astype('int32')
                            cell_x = np.floor(true_boxes[image_index, box_index, 1] * grid_shapes[detection_layer][0]).astype('int32')

	                       # The index of the anchor within the detection layer
                            anchor_layer_index = anchor_mask[detection_layer].index(anchor_index)

	                       # One-hot encoded arrays representing classes probabilities
                            true_class = true_boxes[image_index, box_index, 4].astype('int32')

	                       # Computing y_true: a list of three numpy array.
                            y_true[detection_layer][image_index, cell_x, cell_y, anchor_layer_index, 0:4] = true_boxes[image_index, box_index, 0:4]
                            y_true[detection_layer][image_index, cell_x, cell_y, anchor_layer_index, 4] = 1
                            y_true[detection_layer][image_index, cell_x, cell_y, anchor_layer_index, 5 + true_class] = 1

                            break

            return y_true

    def compute_input_output(self, group):

        # load images and annotations
        image_group       = self.load_image_group(group)
        annotations_group = self.load_annotations_group(group)

        # check validity of annotations
        image_group, annotations_group = self.filter_annotations(image_group, annotations_group, group)

        # perform preprocessing steps
        image_group, annotations_group = self.preprocess_group(image_group, annotations_group)

        # convert image input from list to numpy array
        image_batch = np.zeros(shape=(len(image_group), ) + image_group[0].shape, dtype=image_group[0].dtype)
        for i in range(len(image_group)):
            image_batch[i] = image_group[i]
        # compute y_true
        y_true = self.compute_y_true(annotations_group)

        return [image_batch, *y_true], np.zeros(self.batch_size)

    def __next__(self):
        return self.next()

    def next(self):
        # advance the group index
        with self.lock:
            if self.group_index == 0 and self.shuffle_groups:
                # shuffle groups at start of epoch
                random.shuffle(self.groups)
            group = self.groups[self.group_index]
            self.group_index = (self.group_index + 1) % len(self.groups)

        return self.compute_input_output(group)
