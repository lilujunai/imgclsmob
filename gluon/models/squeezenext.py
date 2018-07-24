"""
    SqueezeNext, implemented in Gluon.
    Original paper: 'SqueezeNext: Hardware-Aware Neural Network Design'
"""

from mxnet import cpu
from mxnet.gluon import nn, HybridBlock


class SqnxtConv(HybridBlock):

    def __init__(self,
                 in_channels,
                 out_channels,
                 kernel_size,
                 strides,
                 padding=(0, 0),
                 **kwargs):
        super(SqnxtConv, self).__init__(**kwargs)
        with self.name_scope():
            self.conv = nn.Conv2D(
                channels=out_channels,
                kernel_size=kernel_size,
                strides=strides,
                padding=padding,
                in_channels=in_channels)
            self.bn = nn.BatchNorm(in_channels=out_channels)
            self.activ = nn.Activation('relu')

    def hybrid_forward(self, F, x):
        x = self.conv(x)
        x = self.bn(x)
        x = self.activ(x)
        return x


class SqnxtBlock(HybridBlock):

    def __init__(self,
                 in_channels,
                 out_channels,
                 strides,
                 **kwargs):
        super(SqnxtBlock, self).__init__(**kwargs)
        if strides == 2:
            reduction_den = 1
            self.reduce = True
        elif in_channels > out_channels:
            reduction_den = 4
            self.reduce = True
        else:
            reduction_den = 2
            self.reduce = False

        with self.name_scope():
            self.conv1 = SqnxtConv(
                in_channels=in_channels,
                out_channels=(in_channels // reduction_den),
                kernel_size=1,
                strides=strides)
            self.conv2 = SqnxtConv(
                in_channels=(in_channels // reduction_den),
                out_channels=(in_channels // (2 * reduction_den)),
                kernel_size=1,
                strides=1)
            self.conv3 = SqnxtConv(
                in_channels=(in_channels // (2 * reduction_den)),
                out_channels=(in_channels // reduction_den),
                kernel_size=(1, 3),
                strides=1,
                padding=(0, 1))
            self.conv4 = SqnxtConv(
                in_channels=(in_channels // reduction_den),
                out_channels=(in_channels // reduction_den),
                kernel_size=(3, 1),
                strides=1,
                padding=(1, 0))
            self.conv5 = SqnxtConv(
                in_channels=(in_channels // reduction_den),
                out_channels=out_channels,
                kernel_size=1,
                strides=1)

            if self.reduce:
                self.shortcut = SqnxtConv(
                    in_channels=in_channels,
                    out_channels=out_channels,
                    kernel_size=1,
                    strides=strides)
            self.activ = nn.Activation('relu')

    def hybrid_forward(self, F, x):
        identity = x
        x = self.conv1(x)
        x = self.conv2(x)
        x = self.conv3(x)
        x = self.conv4(x)
        x = self.conv5(x)
        if self.reduce:
            x = x + self.shortcut(identity)
        else:
            x = x + self.activ(identity)
        x = self.activ(x)
        return x


class SqueezeNext(HybridBlock):

    def __init__(self,
                 width_x,
                 blocks,
                 classes=1000,
                 **kwargs):
        super(SqueezeNext, self).__init__(**kwargs)
        input_channels = 3
        in_channels = 64
        out_channels_per_stage = [32, 64, 128, 256]
        strides_per_stage = [1, 2, 2, 2]

        with self.name_scope():
            self.features = nn.HybridSequential(prefix='')
            self.features.add(SqnxtConv(
                in_channels=input_channels,
                out_channels=int(width_x * in_channels),
                kernel_size=7,
                strides=2,
                padding=1))
            self.features.add(nn.MaxPool2D(
                pool_size=3,
                strides=2,
                ceil_mode=True))
            for i in range(len(blocks)):
                stage = nn.HybridSequential(prefix='')
                strides_i = [strides_per_stage[i]] + [1] * (blocks[i] - 1)
                for j in range(len(strides_i)):
                    stage.add(SqnxtBlock(
                        in_channels=int(width_x * in_channels),
                        out_channels=int(width_x * out_channels_per_stage[i]),
                        strides=strides_i[j]))
                    if j == 0:
                        in_channels = out_channels_per_stage[i]
                self.features.add(stage)

            self.features.add(SqnxtConv(
                in_channels=int(width_x * in_channels),
                out_channels=int(width_x * 128),
                kernel_size=1,
                strides=1))
            self.output = nn.HybridSequential(prefix='')
            self.output.add(nn.AvgPool2D(pool_size=7))
            self.output.add(nn.Flatten())
            self.output.add(nn.Dense(
                units=classes,
                in_units=int(width_x * 128)))

    def hybrid_forward(self, F, x):
        x = self.features(x)
        x = self.output(x)
        return x


def get_squeezenext(arch_type,
                    scale,
                    pretrained=False,
                    ctx=cpu(),
                    **kwargs):
    if arch_type == '23':
        blocks = [6, 6, 8, 1]
    elif arch_type == '23v5':
        blocks = [2, 4, 14, 1]
    else:
        raise ValueError("Unsupported SqueezeNet architecture type {}".format(arch_type))

    if pretrained:
        raise ValueError("Pretrained model is not supported")

    return SqueezeNext(
        width_x=scale,
        blocks=blocks,
        **kwargs)


def sqnxt23_1_0(**kwargs):
    return get_squeezenext('23', 1.0, **kwargs)


def sqnxt23_1_5(**kwargs):
    return get_squeezenext('23', 1.5, **kwargs)


def sqnxt23_2_0(**kwargs):
    return get_squeezenext('23', 2.0, **kwargs)


def sqnxt23v5_1_0(**kwargs):
    return get_squeezenext('23v5', 1.0, **kwargs)


def sqnxt23v5_1_5(**kwargs):
    return get_squeezenext('23v5', 1.5, **kwargs)


def sqnxt23v5_2_0(**kwargs):
    return get_squeezenext('23v5', 2.0, **kwargs)


if __name__ == "__main__":
    import numpy as np
    import mxnet as mx
    net = sqnxt23_1_5()
    net.initialize(ctx=mx.gpu(0))
    input = mx.nd.zeros((1, 3, 224, 224), ctx=mx.gpu(0))
    output = net(input)
    print("output={}".format(output))

    net_params = net.collect_params()
    weight_count = 0
    for param in net_params.values():
        if param.shape is None:
            continue
        weight_count += np.prod(param.shape)
    print("weight_count={}".format(weight_count))
