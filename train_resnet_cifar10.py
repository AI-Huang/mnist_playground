#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Date    : Feb-03-20 23:44
# @Update  : Nov-04-20 20:57
# @Author  : Kan HUANG (kan.huang@connect.ust.hk)

"""Keras training code

# Environments
tensorflow>=2.1.0

"""

import os
import json
import argparse
from datetime import datetime
from functools import partial
import numpy as np
import tensorflow as tf
from tensorflow.keras.callbacks import CSVLogger, LearningRateScheduler, TensorBoard, ModelCheckpoint
from sklearn.model_selection import train_test_split
from data_loaders.tf_fn.load_cifar10 import load_cifar10, load_cifar10_sequence
from models.tf_fn.model_utils import create_model, create_optimizer, create_model_cifar10
from models.tf_fn.optim_utils import cifar10_scheduler, keras_lr_scheduler


def cmd_parser():
    """parse arguments
    """
    parser = argparse.ArgumentParser()

    def string2bool(string):
        """string2bool
        """
        if string not in ["False", "True"]:
            raise argparse.ArgumentTypeError(
                f"""input(={string}) NOT in ["False", "True"]!""")
        if string == "False":
            return False
        elif string == "True":
            return True
    # parser.add_argument('--model', default='tacotron')
    # parser.add_argument(
    #     '--name', help='Name of the run. Used for logging. Defaults to model name.')

    parser.add_argument('--dataset', type=str, dest='dataset',
                        action='store', default="mnist", help=""".""")
    parser.add_argument('--num_classes', type=int, dest='num_classes',
                        action='store', default=10, help=""".""")
    parser.add_argument('--model_name', type=str, dest='model_name',
                        action='store', default="NoModel", help="""model_name, one of ["ResNet18", "ResNet34", "ResNet50", "ResNet101", "ResNet152", "LeNet5", "AttentionLeNet5"].""")
    parser.add_argument('--n', type=int, dest='n',
                        action='store', default=3, help=""".""")
    parser.add_argument('--version', type=int, dest='version',
                        action='store', default=1, help=""".""")
    parser.add_argument('--batch_size', type=int, dest='batch_size',
                        action='store', default=32, help=""".""")
    parser.add_argument('--seed', type=int, default=np.random.randint(10000), metavar='S',
                        help='random seed (default: numpy.random.randint(10000) )')
    parser.add_argument('--validation_split', type=float, dest='validation_split',
                        action='store', default=0.2, help=""".""")
    parser.add_argument('--norm', action='store_true',
                        help="Whether to normalize the dataset, defaults to True.")

    # Optimization parameters
    parser.add_argument('--epochs', type=int, dest='epochs',
                        action='store', default=100, help=""".""")
    parser.add_argument('--optimizer_name', type=str, dest='optimizer_name',
                        action='store', default="SGD", help=""".""")
    parser.add_argument('--learning_rate', type=float, dest='learning_rate',
                        action='store', default=0.1, help=""".""")
    parser.add_argument('--weight_decay', type=float, dest='weight_decay',
                        action='store', default=0.0001, help=""".""")
    parser.add_argument('--momentum', type=float, dest='momentum',
                        action='store', default=0.9, help=""".""")
    parser.add_argument('--lr_schedule', type=str, dest='lr_schedule',
                        action='store', default="no_schedule", help=""".""")

    # Attention parameters
    parser.add_argument('--attention', type=string2bool, dest='attention',
                        action='store', default=False, help='attention, if true, the model will use Attention.')
    parser.add_argument('--attention_type', type=str, dest='attention_type',
                        action='store', default="official", help="""attention_type, one of ["official", "senet"], used only when --attention flag is set.""")

    args = parser.parse_args()

    if args.attention_type not in ["official", "senet"]:
        raise ValueError(
            f"""args.attention_type {args.attention_type} NOT in ["official", "senet"]""")

    return args


def main():
    # Training settings
    args = cmd_parser()
    print(f"Training arguments: {args}.")
    model_name = args.model_name
    dataset = args.dataset
    batch_size = args.batch_size
    epochs = args.epochs
    learning_rate = args.learning_rate
    optimizer_name = args.optimizer_name
    lr_schedule = args.lr_schedule
    if lr_schedule == "cifar10_scheduler":
        lr_schedule_fn = cifar10_scheduler
    elif lr_schedule == "keras_lr_scheduler":
        lr_schedule_fn = keras_lr_scheduler

    # Check inputs
    resnet_family = ["ResNet18", "ResNet34",
                     "ResNet50", "ResNet101", "ResNet152"]
    available_models = ["LeNet5", "AttentionLeNet5",
                        "LeCunLeNet5"] + resnet_family

    if args.attention:
        if args.attention_type == "senet":
            model_name = "AttentionLeNet5_SeNet"
        elif args.attention_type == "official":
            model_name = "AttentionLeNet5_Official"

    # Prepare data
    cifar10_sequence_train, cifar10_sequence_val, cifar10_sequence_test = \
        load_cifar10_sequence(batch_size=batch_size,
                              shuffle=True,
                              seed=args.seed,
                              norm=args.norm,
                              subtract_pixel_mean=True,
                              validation_split=args.validation_split,
                              to_categorical=True,
                              data_augmentation=False)

    # Set random seed
    try:
        tf.keras.utils.set_random_seed(args.seed)
    except:
        import random
        random.seed(args.seed)
        np.random.seed(args.seed)
        tf.random.set_seed(args.seed)

    # Setup model
    batch_x, batch_y = cifar10_sequence_train[0]
    input_shape = batch_x.shape[1:]  # Input image dimensions.
    if args.dataset == "mnist":
        if args.model_name not in available_models:
            raise ValueError(
                f"""args.model_name {args.model_name} NOT in {available_models}""")
        # Preprocessing and choose optimizer for ResNet18
        if model_name in resnet_family:
            model_core = create_model(
                model_name, input_shape=input_shape, num_classes=args.num_classes)

            input_ = tf.keras.layers.Input(input_shape, dtype=tf.uint8)
            x = tf.cast(input_, tf.float32)
            # padding 28x28 to 32x32
            x = tf.pad(x, paddings=[[0, 0], [2, 2], [2, 2], [0, 0]])
            x = model_core(x)
            model = tf.keras.Model(inputs=[input_], outputs=[x])
    elif args.dataset == "cifar10":
        # Model version
        # Orig paper: version = 1 (ResNet v1), Improved ResNet: version = 2 (ResNet v2)
        version = 1
        n = args.n
        # Computed depth from supplied model parameter n
        if version == 1:
            depth = n * 6 + 2
        elif version == 2:
            depth = n * 9 + 2
        args.depth = depth
        model = create_model_cifar10(
            input_shape=input_shape, depth=args.depth, version=args.version)
        # Model name, depth and version
        model_name = 'ResNet%dv%d_CIFAR10' % (depth, version)
    else:
        model = create_model(
            model_name, input_shape=input_shape, num_classes=args.num_classes)

    # Config paths
    date_time = datetime.now().strftime("%Y%m%d-%H%M%S")
    prefix = os.path.join("~", "Documents", "DeepLearningData")
    subfix = os.path.join(
        dataset, model_name, f"b{batch_size}-e{epochs}-lr{learning_rate}", optimizer_name, date_time)
    ckpt_dir = os.path.expanduser(os.path.join(prefix, subfix, "ckpts"))
    log_dir = os.path.expanduser(os.path.join(prefix, subfix, "logs"))
    os.makedirs(ckpt_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, "config.json"), 'w', encoding='utf8') as json_file:
        json.dump(vars(args), json_file, ensure_ascii=False)

    optimizer = create_optimizer(args.optimizer_name,
                                 learning_rate=args.learning_rate,
                                 weight_decay=args.weight_decay,
                                 momentum=args.momentum)
    lr_scheduler = LearningRateScheduler(lr_schedule_fn, verbose=1)

    loss = tf.keras.losses.CategoricalCrossentropy(
        name="categorical_crossentropy")
    from tensorflow.keras.metrics import BinaryAccuracy, CategoricalAccuracy
    metrics = [BinaryAccuracy(name="binary_accuracy"),
               CategoricalAccuracy(name="categorical_accuracy")]

    model.compile(loss=loss,
                  optimizer=optimizer,
                  metrics=metrics)

    # Define callbacks
    csv_logger = CSVLogger(os.path.join(
        log_dir, "training.log.csv"), append=True)
    tensorboard_callback = tf.keras.callbacks.TensorBoard(
        log_dir, histogram_freq=1, update_freq="batch")

    ckpt_filename = "%s-epoch-{epoch:03d}-categorical_accuracy-{categorical_accuracy:.4f}.h5" % model_name
    ckpt_filepath = os.path.join(ckpt_dir, ckpt_filename)
    checkpoint_callback = ModelCheckpoint(
        filepath=ckpt_filepath,
        monitor="categorical_accuracy",
        verbose=1,
        save_weights_only=True
    )

    callbacks = [csv_logger, lr_scheduler,
                 checkpoint_callback, tensorboard_callback]

    # Some bugs may exist in cifar10_sequence_train!
    # Fit model
    # model.fit(
    #     cifar10_sequence_train,
    #     validation_data=cifar10_sequence_val,
    #     epochs=epochs,
    #     batch_size=batch_size,
    #     callbacks=callbacks
    # )

    data_augmentation = False
    if not data_augmentation:
        print('Not using data augmentation.')

        (x_train, y_train), (x_test, y_test) = load_cifar10()

        if args.validation_split > 0:
            print(f"Using validation_split: {args.validation_split}.")
            x_train, x_val, y_train, y_val = train_test_split(
                x_train, y_train,
                test_size=args.validation_split, random_state=args.seed)

        model.fit(x_train, y_train,
                  batch_size=batch_size,
                  epochs=epochs,
                  validation_data=(x_test, y_test),
                  shuffle=True,
                  callbacks=callbacks)


if __name__ == "__main__":
    main()
