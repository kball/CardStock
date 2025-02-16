import os
import wx
import generator
from math import pi
from uiView import *
from codeRunnerThread import RunOnMain


class UiImage(UiView):
    """
    This class is a controller that coordinates management of an image view, based on data from an ImageModel.
    An image does not use its own wx.Window as a view, but instead draws itself onto the stack view.
    """

    imgCache = {}

    def __init__(self, parent, stackManager, model):
        super().__init__(parent, stackManager, model, None)
        self.rotatedBitmap = None
        self.origImage = self.GetImg(model)

    def AspectStrToInt(self, str):
        if str == "Center":
            return 0
        elif str == "Stretch":
            return 1
        elif str == "Scale":
            return 3
        else:
            return 3 # Default to Scale

    def GetImg(self, model):
        file = model.GetProperty("file")
        filepath = self.stackManager.resPathMan.GetAbsPath(file)

        if filepath in self.imgCache:
            img = self.imgCache[filepath]
        else:
            if filepath and os.path.exists(filepath):
                img = wx.Image(filepath, wx.BITMAP_TYPE_ANY)
                self.imgCache[filepath] = img
            else:
                img = None
        return img

    def MakeScaledAndRotatedBitmap(self):
        img = self.origImage
        if not img:
            return None

        xFlipped = self.model.GetProperty("xFlipped")
        yFlipped = self.model.GetProperty("yFlipped")
        rot = self.model.GetProperty("rotation")
        imgSize = img.GetSize()
        viewSize = self.model.GetProperty("size")
        fit = self.model.GetProperty("fit")

        if xFlipped or yFlipped:
            if xFlipped:
                img = img.Mirror(horizontally=True)
            if yFlipped:
                img = img.Mirror(horizontally=False)
        if rot != 0:
            val = float(rot * -pi/180)  # make positive value rotate clockwise
            img = img.Rotate(val, list(img.GetSize()/2))   # use original center
            imgSize = img.GetSize()

        if fit == "Stretch":
            img = img.Scale(viewSize.width, viewSize.height, quality=wx.IMAGE_QUALITY_HIGH)
        elif fit == "Contain":
            scaleX = viewSize.width / imgSize.width
            scaleY = viewSize.height / imgSize.height
            scale = min(scaleX, scaleY)
            img = img.Scale(imgSize.width * scale, imgSize.height * scale, quality=wx.IMAGE_QUALITY_HIGH)
        elif fit == "Fill":
            scaleX = viewSize.width / imgSize.width
            scaleY = viewSize.height / imgSize.height
            scale = max(scaleX, scaleY)
            img = img.Scale(imgSize.width * scale, imgSize.height * scale, quality=wx.IMAGE_QUALITY_HIGH)
            imgSize = img.GetSize()

        if fit in ["Center", "Fill"]:
            offX = 0 if imgSize.Width <= viewSize.Width else ((imgSize.Width - viewSize.Width) / 2)
            offY = 0 if imgSize.Height <= viewSize.Height else ((imgSize.Height - viewSize.Height) / 2)
            w = imgSize.width if imgSize.Width <= viewSize.Width else viewSize.Width
            h = imgSize.height if imgSize.Height <= viewSize.Height else viewSize.Height
            img = img.GetSubImage(wx.Rect(offX, offY, w, h))

        self.rotatedBitmap = img.ConvertToBitmap(32)

    def OnPropertyChanged(self, model, key):
        super().OnPropertyChanged(model, key)

        if key in ["size", "rotation", "fit", "file", "xFlipped", "yFlipped"]:
            self.rotatedBitmap = None
            self.stackManager.view.Refresh()

        if key == "file":
            self.origImage = self.GetImg(self.model)
            self.rotatedBitmap = None
            self.stackManager.view.Refresh()
        elif key == "fit":
            self.stackManager.view.Refresh()
        elif key == "rotation":
            if model.GetProperty("file") != "":
                self.stackManager.view.Refresh()

    def Paint(self, gc):
        if self.origImage:
            if not self.rotatedBitmap:
                self.MakeScaledAndRotatedBitmap()
            r = self.model.GetAbsoluteFrame()

            imgSize = self.rotatedBitmap.GetSize()
            viewSize = r.Size
            offX = 0 if (imgSize.Width >= viewSize.Width) else ((viewSize.Width - imgSize.Width) / 2)
            offY = 0 if (imgSize.Height >= viewSize.Height) else ((viewSize.Height - imgSize.Height) / 2)
            gc.DrawBitmap(self.rotatedBitmap, r.Left + offX, r.Bottom - offY)

        if self.stackManager.isEditing:
            gc.SetPen(wx.Pen('Gray', 1, wx.PENSTYLE_DOT))
            gc.SetBrush(wx.TRANSPARENT_BRUSH)
            gc.DrawRectangle(self.model.GetAbsoluteFrame())


class ImageModel(ViewModel):
    """
    This is the model for an Image object.
    """

    minSize = wx.Size(2, 2)

    def __init__(self, stackManager):
        super().__init__(stackManager)
        self.type = "image"
        self.proxyClass = Image

        self.properties["name"] = "image_1"
        self.properties["file"] = ""
        self.properties["fit"] = "Contain"
        self.properties["rotation"] = 0
        self.properties["xFlipped"] = False
        self.properties["yFlipped"] = False

        self.propertyTypes["file"] = "file"
        self.propertyTypes["fit"] = "choice"
        self.propertyChoices["fit"] = ["Center", "Stretch", "Contain", "Fill"]
        self.propertyTypes["rotation"] = "int"
        self.propertyTypes["xFlipped"] = "bool"
        self.propertyTypes["yFlipped"] = "bool"

        # Custom property order and mask for the inspector
        self.propertyKeys = ["name", "file", "fit", "rotation", "position", "size"]

    def SetProperty(self, key, value, notify=True):
        if key == "rotation":
            value = value % 360
        super().SetProperty(key, value, notify)

    def PerformFlips(self, fx, fy, notify=True):
        if fx:
            self.SetProperty("xFlipped", not self.GetProperty("xFlipped"), notify=notify)
        if fy:
            self.SetProperty("yFlipped", not self.GetProperty("yFlipped"), notify=notify)


class Image(ViewProxy):
    """
    Image proxy objects are the user-accessible objects exposed to event handler code for image objects.
    """

    @property
    def file(self):
        model = self._model
        if not model: return ""
        return model.GetProperty("file")
    @file.setter
    def file(self, val):
        if not isinstance(val, str):
            raise TypeError("file must be a string")
        model = self._model
        if not model: return
        model.SetProperty("file", val)

    @property
    def rotation(self):
        model = self._model
        if not model: return 0
        return model.GetProperty("rotation")
    @rotation.setter
    def rotation(self, val):
        if not (isinstance(val, int) or isinstance(val, float)):
            raise TypeError("rotation must be a number")
        model = self._model
        if not model: return
        model.SetProperty("rotation", val)

    @property
    def fit(self):
        model = self._model
        if not model: return ""
        return model.GetProperty("fit")
    @fit.setter
    def fit(self, val):
        if not isinstance(val, str):
            raise TypeError("fit must be a string")
        model = self._model
        if not model: return
        model.SetProperty("fit", val)

    def AnimateRotation(self, duration, endRotation, onFinished=None, *args, **kwargs):
        if not (isinstance(duration, int) or isinstance(duration, float)):
            raise TypeError("duration must be a number")
        if not (isinstance(endRotation, int) or isinstance(endRotation, float)):
            raise TypeError("endRotation must be a number")

        model = self._model
        if not model: return

        def onStart(animDict):
            origVal = self.rotation
            animDict["origVal"] = origVal
            animDict["offset"] = endRotation - origVal

        def onUpdate(progress, animDict):
            model.SetProperty("rotation", animDict["origVal"] + animDict["offset"] * progress)

        def internalOnFinished(animDict):
            if onFinished: self._model.stackManager.runner.EnqueueFunction(onFinished, *args, **kwargs)

        model.AddAnimation("rotation", duration, onUpdate, onStart, internalOnFinished)
