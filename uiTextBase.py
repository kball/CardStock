import wx
import wx.stc as stc
from uiView import *
from killableThread import RunOnMain


class UiTextBase(UiView):
    """
    This class is the abstract base controller for UiTextLabel and UiTextField.
    """

    def __init__(self, parent, stackManager, model, view):
        super().__init__(parent, stackManager, model, view)
        self.isInlineEditing = False
        self.inlineEditor = None
        self.font = None
        self.textColor = None

    def DestroyView(self):
        self.StopInlineEditing()
        super().DestroyView()

    def OnPropertyChanged(self, model, key):
        super().OnPropertyChanged(model, key)
        if key == "text":
            if self.model.type == "textlabel":
                self.stackManager.view.Refresh(True)
            else:
                if self.view:
                    wasEditable = self.view.IsEditable()
                    if not wasEditable:
                        self.view.SetEditable(True)
                    self.view.ChangeValue(str(self.model.GetProperty(key)))
                    self.view.SetEditable(wasEditable)
                    self.view.Refresh(True)
            self.OnResize(None)
        elif key in ["font", "fontSize", "textColor"]:
            self.UpdateFont(model, self.view)
            self.OnResize(None)
            if self.view:
                self.view.Refresh(True)
        elif key == "alignment":
            if self.model.type == "textlabel":
                self.stackManager.view.Refresh(True)
            else:
                self.stackManager.SelectUiView(None)
                self.stackManager.LoadCardAtIndex(self.stackManager.cardIndex, reload=True)
                self.stackManager.SelectUiView(self.stackManager.GetUiViewByModel(self.model))

    def UpdateFont(self, model, view):
        familyName = model.GetProperty("font")
        platformScale = 1.4 if (wx.Platform == '__WXMAC__') else 1.0
        size = int(model.GetProperty("fontSize") * platformScale)
        font = wx.Font(wx.FontInfo(size).Family(self.FamilyForName(familyName)))
        color = wx.Colour(model.GetProperty("textColor"))
        if color.IsOk():
            colorStr = color.GetAsString(flags=wx.C2S_HTML_SYNTAX)
        else:
            colorStr = 'black'

        if view == None:
            self.font = font
            self.textColor = colorStr
            self.stackManager.view.Refresh(True)
        elif not isinstance(view, stc.StyledTextCtrl):
            view.SetFont(font)
            view.SetForegroundColour(colorStr)
        else:
            fontName = font.GetNativeFontInfoUserDesc()
            if "'" in fontName:
                # Multi-word faceName gets single-quoted
                fontName = font.GetNativeFontInfoUserDesc().split("'")[1]
            else:
                fontName = font.GetNativeFontInfoUserDesc().split(" ")[0]
            spec = f"fore:{colorStr},face:{fontName},size:{size}"
            view.StyleSetSpec(stc.STC_STYLE_DEFAULT, spec)
            view.StyleClearAll()

    def StartInlineEditing(self):
        # Show a temporary StyledTextCtrl with the same frame and font as the label
        text = self.model.GetProperty("text")
        field = stc.StyledTextCtrl(parent=self.stackManager.view, style=wx.BORDER_SIMPLE | stc.STC_WRAP_WORD)
        field.SetUseHorizontalScrollBar(False)
        field.SetUseVerticalScrollBar(False)
        field.SetWrapMode(stc.STC_WRAP_WORD)
        field.SetMarginWidth(1, 0)
        rect = self.model.GetAbsoluteFrame().Inflate(1)
        rect.width += 20
        field.SetRect(self.stackManager.ConvRect(rect))
        field.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        field.Bind(stc.EVT_STC_ZOOM, self.OnZoom)
        self.UpdateFont(self.model, field)
        if self.view:
            self.view.Hide()
        field.ChangeValue(text)
        field.EmptyUndoBuffer()
        field.SetFocus()
        self.inlineEditor = field
        self.isInlineEditing = True
        self.stackManager.inlineEditingView = self

    def OnKeyDown(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.StopInlineEditing()
        event.Skip()

    def OnZoom(self, event):
        z = event.GetEventObject().GetZoom()
        if z != 0:
            event.GetEventObject().SetZoom(0)

    def StopInlineEditing(self):
        if self.stackManager.isEditing and self.isInlineEditing:
            if self.view:
                self.view.Show()
            self.model.SetProperty("text", self.inlineEditor.GetValue())
            self.stackManager.view.RemoveChild(self.inlineEditor)
            wx.CallAfter(self.inlineEditor.Destroy)
            self.inlineEditor = None
            self.isInlineEditing = False
            self.stackManager.inlineEditingView = None
            self.stackManager.view.SetFocus()
            self.stackManager.view.Refresh()

    @staticmethod
    def FamilyForName(name):
        if name == "Serif":
            return wx.FONTFAMILY_ROMAN
        if name == "Sans-Serif":
            return wx.FONTFAMILY_SWISS
        if name == "Fancy":
            return wx.FONTFAMILY_DECORATIVE
        if name == "Script":
            return wx.FONTFAMILY_SCRIPT
        if name == "Modern":
            return wx.FONTFAMILY_MODERN
        if name == "Mono":
            return wx.FONTFAMILY_TELETYPE
        return wx.FONTFAMILY_DEFAULT


class TextBaseModel(ViewModel):
    """
    This is the model for a TextLabel object.
    """

    def __init__(self, stackManager):
        super().__init__(stackManager)
        self.type = None
        self.proxyClass = None

        self.properties["text"] = "Text"
        self.properties["alignment"] = "Left"
        self.properties["textColor"] = "black"
        self.properties["font"] = "Default"
        self.properties["fontSize"] = 18

        self.propertyTypes["text"] = "string"
        self.propertyTypes["alignment"] = "choice"
        self.propertyTypes["textColor"] = "color"
        self.propertyTypes["font"] = "choice"
        self.propertyTypes["fontSize"] = "int"
        self.propertyChoices["alignment"] = ["Left", "Center", "Right"]
        self.propertyChoices["font"] = ["Default", "Serif", "Sans-Serif", "Mono"]

        # Custom property order and mask for the inspector
        self.propertyKeys = ["name", "text", "alignment", "font", "fontSize", "textColor", "position", "size"]


class TextBaseProxy(ViewProxy):
    """
    TextBaseProxy objects are the abstract base class of the user-accessible objects exposed to event handler code for
    text labels and text fields.
    """

    @property
    def text(self):
        return self._model.GetProperty("text")
    @text.setter
    def text(self, val):
        self._model.SetProperty("text", str(val))

    @property
    def alignment(self):
        return self._model.GetProperty("alignment")
    @alignment.setter
    def alignment(self, val):
        if not isinstance(val, str):
            raise TypeError("alignment must be a string")
        self._model.SetProperty("alignment", val)

    @property
    def textColor(self):
        return self._model.GetProperty("textColor")
    @textColor.setter
    def textColor(self, val):
        if not isinstance(val, str):
            raise TypeError("textColor must be a string")
        self._model.SetProperty("textColor", val)

    @property
    def font(self):
        return self._model.GetProperty("font")
    @font.setter
    def font(self, val):
        if not isinstance(val, str):
            raise TypeError("font must be a string")
        self._model.SetProperty("font", val)

    @property
    def fontSize(self):
        return self._model.GetProperty("fontSize")
    @fontSize.setter
    def fontSize(self, val):
        if not (isinstance(val, int) or isinstance(val, float)):
            raise TypeError("fontSize must be a number")
        self._model.SetProperty("fontSize", val)

    def AnimateTextColor(self, duration, endVal, onFinished=None, *args, **kwargs):
        if not (isinstance(duration, int) or isinstance(duration, float)):
            raise TypeError("duration must be a number")
        if not isinstance(endVal, str):
            raise TypeError("endColor must be a string")

        @RunOnMain
        def func():
            origVal = wx.Colour(self.textColor)
            endValue = wx.Colour(endVal)

            def internalOnFinished():
                if onFinished: onFinished(*args, **kwargs)

            if origVal.IsOk() and endValue.IsOk() and endValue != origVal:
                origParts = [origVal.Red(), origVal.Green(), origVal.Blue(), origVal.Alpha()]
                endParts = [endValue.Red(), endValue.Green(), endValue.Blue(), endValue.Alpha()]
                offsets = [endParts[i]-origParts[i] for i in range(4)]
                def f(progress):
                    self._model.SetProperty("textColor", [origParts[i]+offsets[i]*progress for i in range(4)])
                self._model.AddAnimation("textColor", duration, f, internalOnFinished)
            else:
                self._model.AddAnimation("textColor", duration, None, internalOnFinished)
        func()
