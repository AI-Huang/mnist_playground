export PYTHONPATH="${PYTHONPATH}:./"

# std_norm_pad_crop
date_time=$(date "+%Y%m%d-%H%M%S")
for ((i=1;i<=5;i++)); do
# --seed=42
# --batch_size=32
# --optimizer_name=SGD
# --learning_rate=0.1
# --lr_schedule=cifar10_schedule
# discuss on data_augmentation
# --data_augmentation=pad_crop, random_translation
python ./scripts/train_resnet_cifar10_tf.py --n=3 --version=1 --dataset=cifar10 --data_preprocessing=std_norm --data_augmentation=random_translation --validation_split=0.1 --batch_size=128 --epochs=200 --learning_rate=0.1 --optimizer_name=SGD  --weight_decay=0.0001 --momentum=0.9 --lr_schedule=cifar10_schedule --date_time=${date_time} --run=${i};
done
