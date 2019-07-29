import torch
import torch.nn as nn
import torch.nn.functional as F
import math

class double_conv(nn.Module):
    '''(conv => BN => ReLU) * 2'''

    def __init__(self, in_ch, out_ch):
        super(double_conv, self).__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True)
        )

    def forward(self, x):
        x = self.conv(x)
        return x


class inconv(nn.Module):
    def __init__(self, in_ch, out_ch):
        super(inconv, self).__init__()
        self.conv = double_conv(in_ch, out_ch)

    def forward(self, x):
        x = self.conv(x)
        return x


class down(nn.Module):
    def __init__(self, in_ch, out_ch):
        super(down, self).__init__()
        self.mpconv = nn.Sequential(
            nn.MaxPool2d(2),
            double_conv(in_ch, out_ch)
        )

    def forward(self, x):
        x = self.mpconv(x)
        return x


class up(nn.Module):
    def __init__(self, in_ch, out_ch, bilinear=True):
        super(up, self).__init__()

        #  would be a nice idea if the upsampling could be learned too,
        #  but my machine do not have enough memory to handle all those weights
        if bilinear:
            self.up = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
        else:
            self.up = nn.ConvTranspose2d(in_ch // 2, in_ch // 2, 2, stride=2)

        self.conv = double_conv(in_ch, out_ch)

    def forward(self, x1, x2):
        x1 = self.up(x1)

        # input is CHW
        diffY = x2.size()[2] - x1.size()[2]
        diffX = x2.size()[3] - x1.size()[3]

        x1 = F.pad(x1, (diffX // 2, diffX - diffX // 2,
                        diffY // 2, diffY - diffY // 2))

        # for padding issues, see
        # https://github.com/HaiyongJiang/U-Net-Pytorch-Unstructured-Buggy/commit/0e854509c2cea854e247a9c615f175f76fbb2e3a
        # https://github.com/xiaopeng-liao/Pytorch-UNet/commit/8ebac70e633bac59fc22bb5195e513d5832fb3bd

        x = torch.cat([x2, x1], dim=1)
        x = self.conv(x)
        return x


class outconv(nn.Module):
    def __init__(self, in_ch, out_ch):
        super(outconv, self).__init__()
        self.conv = nn.Conv2d(in_ch, out_ch, 1)

    def forward(self, x):
        x = self.conv(x)
        return x




class UNet(nn.Module):
    def __init__(self, n_channels, n_classes):
        super(UNet, self).__init__()
        self.inc = inconv(n_channels, 64)
        self.down1 = down(64, 128)
        self.down2 = down(128, 256)
        self.down3 = down(256, 512)
        self.down4 = down(512, 512)
        self.up1 = up(1024, 256)
        self.up2 = up(512, 128)
        self.up3 = up(256, 64)
        self.up4 = up(128, 64)
        self.outc = outconv(64, n_classes)

    def forward(self, x):
        x1 = self.inc(x)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        x4 = self.down3(x3)
        x5 = self.down4(x4)
        x = self.up1(x5, x4)
        x = self.up2(x, x3)
        x = self.up3(x, x2)
        x = self.up4(x, x1)
        x = self.outc(x)
        return x


def conv3x3(in_planes, out_planes, stride=1):
    """3x3 convolution with padding"""
    return nn.Conv2d(in_planes, out_planes, kernel_size=3, stride=stride, padding=1, bias=False)


class BasicBlock(nn.Module):
    expansion = 1

    def __init__(self, inplanes, planes, stride=1, downsample=None):
        super(BasicBlock, self).__init__()
        self.conv1 = conv3x3(inplanes, planes, stride)
        self.bn1 = nn.BatchNorm2d(planes)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = conv3x3(planes, planes)
        self.bn2 = nn.BatchNorm2d(planes)
        self.downsample = downsample
        self.stride = stride

    def forward(self, x):
        residual = x

        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)

        if self.downsample is not None:
            residual = self.downsample(x)

        out += residual
        out = self.relu(out)

        return out


class Bottleneck(nn.Module):

    def __init__(self, inplanes, planes, stride=1):
        super(Bottleneck, self).__init__()

        # residual path
        self.conv1 = nn.Conv2d(inplanes, planes, kernel_size=1, bias=False)
        self.bn1 = nn.BatchNorm2d(planes)

        self.conv2 = nn.Conv2d(planes, planes, kernel_size=3, stride=stride, padding=1, bias=False)

        self.bn2 = nn.BatchNorm2d(planes)
        self.conv3 = nn.Conv2d(planes, planes, kernel_size=1, bias=False)
        self.bn3 = nn.BatchNorm2d(planes)
        self.relu = nn.ReLU(inplace=True)
        self.stride = stride

        # if stride >1, then we need to subsamble the input
        if stride > 1:
            self.shortcut = nn.Conv2d(inplanes, planes, kernel_size=1, stride=stride, bias=False)
        else:
            self.shortcut = None

    def forward(self, x):

        if self.shortcut is None:
            bypass = x
        else:
            bypass = self.shortcut(x)

        residual = self.conv1(x)
        residual = self.bn1(residual)
        residual = self.relu(residual)

        residual = self.conv2(residual)
        residual = self.bn2(residual)
        residual = self.relu(residual)

        residual = self.conv3(residual)
        residual = self.bn3(residual)

        out = bypass + residual
        out = self.relu(out)

        return out


class DoubleResNet(nn.Module):
    def __init__(self, inplanes, planes, stride=1):
        super(DoubleResNet, self).__init__()
        self.res1 = Bottleneck(inplanes, planes, stride)
        self.res2 = Bottleneck(planes, planes, 1)

    def forward(self, x):
        out = self.res1(x)
        out = self.res2(out)
        return out


class ConvTransposeLayer(nn.Module):
    def __init__(self, inplanes, outplanes, stride=2):
        super(ConvTransposeLayer, self).__init__()
        self.res = Bottleneck(inplanes, inplanes, stride=1)
        self.deconv = nn.ConvTranspose2d(inplanes, outplanes, kernel_size=3, stride=2, padding=1, bias=False)

    def forward(self, x, output_size):
        out = self.res(x)
        out = self.deconv(out, output_size=output_size)
        return out


class UResNet(nn.Module):

    def __init__(self, num_classes=3, input_channels=3, inplanes=16, showsizes=False):
        self.inplanes = inplanes
        super(UResNet, self).__init__()

        self._showsizes = showsizes  # print size at each layer

        # Encoder

        # stem
        # one big stem
        # self.conv1 = nn.Conv2d(input_channels, self.inplanes, kernel_size=7, stride=1, padding=3, bias=True) # initial conv layer
        # self.bn1 = nn.BatchNorm2d(self.inplanes)
        # self.relu1 = nn.ReLU(inplace=True)

        # 7x7 = (3x3)^3
        self.conv1 = nn.Conv2d(input_channels, self.inplanes, kernel_size=3, stride=1, padding=1,
                               bias=True)  # initial conv layer
        self.bn1 = nn.BatchNorm2d(self.inplanes)
        self.relu1 = nn.ReLU(inplace=True)

        self.conv2 = nn.Conv2d(self.inplanes, self.inplanes, kernel_size=3, stride=1, padding=1,
                               bias=True)  # initial conv layer
        self.bn2 = nn.BatchNorm2d(self.inplanes)
        self.relu2 = nn.ReLU(inplace=True)

        self.conv3 = nn.Conv2d(self.inplanes, self.inplanes, kernel_size=3, stride=1, padding=1,
                               bias=True)  # initial conv layer
        self.bn3 = nn.BatchNorm2d(self.inplanes)
        self.relu3 = nn.ReLU(inplace=True)

        self.enc_layer1 = self._make_encoding_layer(self.inplanes * 1, self.inplanes * 2, stride=2)
        self.enc_layer2 = self._make_encoding_layer(self.inplanes * 2, self.inplanes * 4, stride=2)
        self.enc_layer3 = self._make_encoding_layer(self.inplanes * 4, self.inplanes * 8, stride=2)
        self.enc_layer4 = self._make_encoding_layer(self.inplanes * 8, self.inplanes * 16, stride=2)

        self.dec_layer4 = self._make_decoding_layer(self.inplanes * 16, self.inplanes * 8, stride=2)
        self.dec_layer3 = self._make_decoding_layer(self.inplanes * 8 * 2, self.inplanes * 4, stride=2)
        self.dec_layer2 = self._make_decoding_layer(self.inplanes * 4 * 2, self.inplanes * 2, stride=2)
        self.dec_layer1 = self._make_decoding_layer(self.inplanes * 2 * 2, self.inplanes * 1, stride=2)

        # final conv stem (7x7) = (3x3)^3
        self.nkernels = 16
        self.conv10 = nn.Conv2d(self.inplanes, self.nkernels, kernel_size=3, stride=1, padding=1,
                                bias=True)  # initial conv layer
        self.bn10 = nn.BatchNorm2d(self.nkernels)
        self.relu10 = nn.ReLU(inplace=True)

        self.conv11 = nn.Conv2d(self.nkernels, self.nkernels * 2, kernel_size=3, stride=1, padding=1,
                                bias=True)  # initial conv layer
        self.bn11 = nn.BatchNorm2d(self.nkernels * 2)
        self.relu11 = nn.ReLU(inplace=True)

        self.conv12 = nn.Conv2d(self.nkernels * 2, self.nkernels, kernel_size=3, stride=1, padding=1,
                                bias=True)  # initial conv layer
        self.bn12 = nn.BatchNorm2d(self.nkernels)
        self.relu12 = nn.ReLU(inplace=True)

        # perceptron
        self.conv13 = nn.Conv2d(self.nkernels, num_classes, kernel_size=1, stride=1, padding=0,
                                bias=True)  # initial conv layer

        # we use log softmax in order to more easily pair it with
        # self.softmax = nn.LogSoftmax(dim=1)  # should return [b,c=3,h,w], normalized over, c dimension

        # initialization
        for m in self.modules():
            if isinstance(m, nn.Conv2d) or isinstance(m, nn.ConvTranspose2d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, math.sqrt(2. / n))
            elif isinstance(m, nn.BatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()

    def _make_encoding_layer(self, inplanes, planes, stride=2):

        return DoubleResNet(inplanes, planes, stride=stride)

    def _make_decoding_layer(self, inplanes, planes, stride=2):
        # return nn.ConvTranspose2d( inplanes, planes, kernel_size=3, stride=2, padding=1, bias=False )
        return ConvTransposeLayer(inplanes, planes, stride)

    def forward(self, x):

        # if self._showsizes:
        #     print
        #     "input: ", x.size(), " is_cuda=", x.is_cuda

        # stem
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu1(x)

        x = self.conv2(x)
        x = self.bn2(x)
        x = self.relu2(x)

        x = self.conv3(x)
        x = self.bn3(x)
        x0 = self.relu3(x)

        # if self._showsizes:
        #     print
        #     "after conv1, x0: ", x0.size()

        x1 = self.enc_layer1(x0)
        x2 = self.enc_layer2(x1)
        x3 = self.enc_layer3(x2)
        x4 = self.enc_layer4(x3)
        # if self._showsizes:
        #     print
        #     "after encoding: "
        #     print
        #     "  x1: ", x1.size()
        #     print
        #     "  x2: ", x2.size()
        #     print
        #     "  x3: ", x3.size()
        #     print
        #     "  x4: ", x4.size()

        x = self.dec_layer4(x4, output_size=x3.size())
        # if self._showsizes:
        #     print
        #     "after decoding:"
        #     print
        #     "  dec4: ", x.size(), " iscuda=", x.is_cuda

        # add skip connection
        x = torch.cat([x, x3], 1)
        # if self._showsizes:
        #     print
        #     "  dec4+x3: ", x.size()
        x = self.dec_layer3(x, output_size=x2.size())
        # if self._showsizes:
        #     print
        #     "  dec3: ", x.size(), " iscuda=", x.is_cuda

        # add skip connection
        x = torch.cat([x, x2], 1)
        # if self._showsizes:
        #     print
        #     "  dec3+x2: ", x.size(), " iscuda=", x.is_cuda

        x = self.dec_layer2(x, output_size=x1.size())
        # if self._showsizes:
        #     print
        #     "  dec2: ", x.size(), " iscuda=", x.is_cuda

        # add skip connection
        x = torch.cat([x, x1], 1)
        # if self._showsizes:
        #     print
        #     "  dec2+x1: ", x.size(), " iscuda=", x.is_cuda

        x = self.dec_layer1(x, output_size=x0.size())
        # if self._showsizes:
        #     print
        #     "  dec1: ", x.size(), " iscuda=", x.is_cuda

        x = self.conv10(x)
        x = self.bn10(x)
        x = self.relu10(x)

        x = self.conv11(x)
        x = self.bn11(x)
        x = self.relu11(x)

        x = self.conv12(x)
        x = self.bn12(x)
        x = self.relu12(x)

        x = self.conv13(x)

        # x = self.softmax(x)
        # if self._showsizes:
        #     print
        #     "  softmax: ", x.size()

        return x

if __name__ == '__main__':
    x = torch.randn((32, 1, 192, 224)).cuda()
    net = UResNet(num_classes=2, input_channels=1, inplanes=16)
    net.cuda()
    y = net(x)