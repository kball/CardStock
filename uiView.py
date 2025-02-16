import threading

import wx
import threading
import ast
import re
import generator
import helpData
from time import time
from codeRunnerThread import RunOnMain, RunOnMainAsync
from cardstockFrameParts import *


class UiView(object):
    """
    This class is an abstract base class for the other Ui objects (view controllers) that coordinate management of
    their views and models.
    """

    def __init__(self, parent, stackManager, model, view):
        super().__init__()
        self.stackManager = stackManager
        self.parent = parent
        self.view = view
        self.model = None
        self.SetModel(model)
        self.hitRegion = None
        self.isSelected = False
        self.hasMouseMoved = False
        self.SetView(view)

        self.lastEditedHandler = None
        self.delta = ((0, 0))

    def __repr__(self):
        if self.model:
            return "<"+str(self.__class__.__name__) + ":" + self.model.type + ":'" + self.model.GetProperty("name")+"'>"
        return "<"+str(self.__class__.__name__)+">"

    def SetDown(self):
        self.DestroyView()
        self.stackManager = None
        self.parent = None
        self.model = None
        self.hitRegion = None

    def BindEvents(self, view):
        view.Bind(wx.EVT_LEFT_DOWN, self.FwdOnMouseDown)
        view.Bind(wx.EVT_LEFT_DCLICK, self.FwdOnMouseDown)
        view.Bind(wx.EVT_MOTION, self.FwdOnMouseMove)
        view.Bind(wx.EVT_LEFT_UP, self.FwdOnMouseUp)
        view.Bind(wx.EVT_KEY_DOWN, self.FwdOnKeyDown)
        view.Bind(wx.EVT_KEY_UP, self.FwdOnKeyUp)

    def FwdOnMouseDown( self, event): self.stackManager.OnMouseDown( self, event)
    def FwdOnMouseMove( self, event): self.stackManager.OnMouseMove( self, event)
    def FwdOnMouseUp(   self, event): self.stackManager.OnMouseUp(   self, event)
    def FwdOnKeyDown(   self, event): self.stackManager.OnKeyDown(   self, event)
    def FwdOnKeyUp(     self, event): self.stackManager.OnKeyUp(     self, event)

    def SetView(self, view):
        self.view = view
        if view:
            if self.GetCursor():
                self.view.SetCursor(wx.Cursor(self.GetCursor()))

            mSize = self.model.GetProperty("size")
            if mSize[0] > 0 and mSize[1] > 0:
                rect = wx.Rect(wx.Point(self.model.GetAbsolutePosition()), mSize)
                self.view.SetRect(self.stackManager.ConvRect(rect))

            self.BindEvents(view)
            view.Bind(wx.EVT_SIZE, self.OnResize)
            self.view.Show(not self.model.IsHidden())

    def SetModel(self, model):
        self.model = model
        self.lastEditedHandler = None

    def GetCursor(self):
        if self.stackManager.isEditing:
            return wx.CURSOR_HAND
        else:
            return None

    def OnPropertyChanged(self, model, key):
        if key == "size":
            s = self.model.GetProperty(key)
            self.ClearHitRegion()
            if self.view:
                rect = wx.Rect(wx.Point(self.model.GetAbsolutePosition()), s)
                self.view.SetRect(self.stackManager.ConvRect(rect))
                self.view.Refresh()
            self.stackManager.view.Refresh()
        elif key == "position":
            pos = wx.Point(self.model.GetAbsolutePosition())
            if self.view:
                rect = wx.Rect(pos, self.model.GetProperty("size"))
                self.view.SetRect(self.stackManager.ConvRect(rect))
                self.view.Refresh()
            self.stackManager.view.Refresh()
            if self.parent.model.type == "group":
                self.parent.ClearHitRegion()
        elif key == "hidden":
            if self.view:
                self.view.Show(not self.model.IsHidden())
            self.stackManager.view.Refresh()

    def OnResize(self, event):
        pass

    def DestroyView(self):
        if self.view:
            if self.view.HasCapture():
                self.view.ReleaseMouse()
            if self.view.GetParent() == self.stackManager.view:
                self.stackManager.view.RemoveChild(self.view)
            self.view.Destroy()
            self.view = None

    def GetSelected(self):
        return self.isSelected

    def SetSelected(self, selected):
        if self.isSelected != selected:
            self.isSelected = selected
            self.ClearHitRegion()
            self.stackManager.view.Refresh()

    def OnMouseDown(self, event):
        if self.stackManager.runner and self.model.GetHandler("OnMouseDown"):
            self.stackManager.runner.RunHandler(self.model, "OnMouseDown", event)
        event.Skip()

    def OnMouseMove(self, event):
        self.hasMouseMoved = True
        event.Skip()

    def OnMouseUpOutside(self, event):
        pass

    def OnMouseUp(self, event):
        if self.stackManager.runner and self.model.GetHandler("OnMouseUp"):
            self.stackManager.runner.RunHandler(self.model, "OnMouseUp", event)
        event.Skip()

    def OnMouseEnter(self, event):
        if self.stackManager.runner and self.model.GetHandler("OnMouseEnter"):
            self.stackManager.runner.RunHandler(self.model, "OnMouseEnter", event)
        event.Skip()

    def OnMouseExit(self, event):
        if self.stackManager and self.stackManager.runner and self.model.GetHandler("OnMouseExit"):
            self.stackManager.runner.RunHandler(self.model, "OnMouseExit", event)
        event.Skip()

    def RunAnimations(self, onFinishedCalls, elapsedTime):
        # Move the object by speed.x and speed.y pixels per second
        updateList = []
        finishList = []
        with self.model.animLock:
            if self.model.type not in ["stack", "card"]:
                speed = self.model.GetProperty("speed")
                if speed != (0,0) and "position" not in self.model.animations:
                    pos = self.model.GetProperty("position")
                    self.model.SetProperty("position", [pos.x + speed.x*elapsedTime, pos.y + speed.y*elapsedTime])

            # Run any in-progress animations
            now = time()
            for (key, animList) in self.model.animations.copy().items():
                animDict = animList[0]
                if "startTime" in animDict:
                    progress = (now - animDict["startTime"]) / animDict["duration"]
                    if progress < 1.0:
                        if animDict["onUpdate"]:
                            updateList.append([animDict, progress])
                    else:
                        if animDict["onUpdate"]:
                            updateList.append([animDict, 1.0])
                        finishList.append(key)
        for (d,p) in updateList:
            d["onUpdate"](p, d)
        for key in finishList:
            self.model.FinishAnimation(key)

    def OnPeriodic(self, event):
        didRun = False
        if self.hasMouseMoved:
            self.hasMouseMoved = False
            if self.stackManager.runner and self.model.GetHandler("OnMouseMove"):
                self.stackManager.runner.RunHandler(self.model, "OnMouseMove", event)
                didRun = True

        if self.stackManager.runner and self.model.GetHandler("OnPeriodic"):
            self.stackManager.runner.RunHandler(self.model, "OnPeriodic", event)
            didRun = True

        return didRun

    def PaintSelectionBox(self, gc):
        if self.isSelected and self.stackManager.tool.name == "hand":
            f = self.model.GetAbsoluteFrame()
            gc.SetPen(wx.Pen('Blue', 3, wx.PENSTYLE_SHORT_DASH))
            gc.SetBrush(wx.TRANSPARENT_BRUSH)
            gc.DrawRectangle(f.Inflate(2))

            gc.SetPen(wx.TRANSPARENT_PEN)
            gc.SetBrush(wx.Brush('blue', wx.BRUSHSTYLE_SOLID))
            for box in self.GetResizeBoxRects():
                gc.DrawRectangle(wx.Rect(box.TopLeft + f.TopLeft, box.Size))

    def Paint(self, gc):
        pass

    def HitTest(self, pt):
        if not self.hitRegion:
            self.MakeHitRegion()
        if self.hitRegion.Contains(pt):
            return self
        return None

    def HasGroupAncestor(self, uiView):
        ui = self
        while ui and ui.model.type not in ["card", "stack"]:
            if ui == uiView:
                return True
            ui = ui.parent
        return False

    def GetResizeBoxRects(self):
        # The returned rects are relative to the position of the object
        # The resize box/handles should hang out of the frame, to allow grabbing it from behind
        # native widgets which can obscure the full frame.
        s = self.model.GetProperty("size")
        return [wx.Rect(-6, -6, 12, 12),
                wx.Rect(s.width - 2, -6, 12, 12),
                wx.Rect(-6, s.height - 2, 12, 12),
                wx.Rect(s.width - 2, s.height - 2, 12, 12)]

    def ClearHitRegion(self):
        self.hitRegion = None
        if self.parent and self.parent.model.type == "group":
            self.parent.ClearHitRegion()

    def GetHitRegion(self):
        if not self.hitRegion:
            self.MakeHitRegion()
        return self.hitRegion

    def MakeHitRegion(self):
        s = self.model.GetProperty("size")
        reg = wx.Region(wx.Rect(0, 0, s.width, s.height))
        if self.stackManager.isEditing and self.isSelected and self.stackManager.tool.name == "hand":
            for r in self.GetResizeBoxRects():
                reg.Union(wx.Region(r.Inflate(2)))
        self.hitRegion = reg

    handlerDisplayNames = {
        'OnSetup':      "OnSetup():",
        'OnShowCard':   "OnShowCard():",
        'OnHideCard':   "OnHideCard():",
        'OnClick':      "OnClick():",
        'OnTextEnter':  "OnTextEnter():",
        'OnTextChanged':"OnTextChanged():",
        'OnMouseDown':  "OnMouseDown(mousePos):",
        'OnMouseMove':  "OnMouseMove(mousePos):",
        'OnMouseUp':    "OnMouseUp(mousePos):",
        'OnMouseEnter': "OnMouseEnter(mousePos):",
        'OnMouseExit':  "OnMouseExit(mousePos):",
        'OnMessage':    "OnMessage(message):",
        'OnKeyDown':    "OnKeyDown(keyName):",
        'OnKeyUp':      "OnKeyUp(keyName):",
        'OnResize':     "OnResize():",
        'OnPeriodic':   "OnPeriodic(elapsedTime):",
    }


class ViewModel(object):
    """
    This is the abstract base class for the other model classes.
    The model holds the property values and event handler text for each object.
    It also holds the type of each property, and the ordered list of properties to display in the inspector.
    It also handles animating properties of the object, like position, size, or color.
    """

    minSize = wx.Size(20, 20)
    reservedNames = helpData.HelpData.ReservedNames()

    def __init__(self, stackManager):
        super().__init__()
        self.type = None
        self.parent = None
        self.handlers = {"OnSetup": "",
                         "OnMouseEnter": "",
                         "OnMouseDown": "",
                         "OnMouseMove": "",
                         "OnMouseUp": "",
                         "OnMouseExit": "",
                         "OnMessage": "",
                         "OnPeriodic": ""
                         }
        self.initialEditHandler = "OnMouseDown"

        self.properties = {"name": "",
                           "size": wx.Size(0,0),
                           "position": wx.RealPoint(0,0),
                           "speed": wx.Point(0,0),
                           "hidden": False,
                           "data": {}
                           }
        self.propertyKeys = ["name", "position", "size"]
        self.propertyTypes = {"name": "string",
                              "position": "floatpoint",
                              "center": "floatpoint",
                              "size": "size",
                              "speed": "point",
                              "hidden": "bool",
                              "data": "dict"
                              }
        self.propertyChoices = {}

        self.childModels = []
        self.stackManager = stackManager
        self.isDirty = False
        self.proxy = None
        self.lastOnPeriodicTime = None
        self.animations = {}
        self.proxyClass = ViewProxy
        self.animLock = threading.Lock()
        self.didSetDown = False

    def __repr__(self):
        return "<"+str(self.__class__.__name__) + ":" + self.type + ":'" + self.GetProperty("name")+"'>"

    def SetBackUp(self, stackManager):
        if self.didSetDown:
            self.stackManager = stackManager
            self.didSetDown = False
            for child in self.childModels:
                child.SetBackUp(stackManager)
                child.parent = self

    def SetDown(self):
        with self.animLock:
            self.didSetDown = True
            for child in self.childModels:
                child.SetDown()
            if self.proxy:
                self.proxy._model = None
                self.proxy = None
            self.animations = {}
            self.stackManager = None
            self.parent = None

    def DismantleChildTree(self):
        for child in self.childModels:
            child.DismantleChildTree()
        self.childModels = None

    def CreateCopy(self):
        data = self.GetData()
        newModel = generator.StackGenerator.ModelFromData(self.stackManager, data)
        if newModel.type != "card":
            self.stackManager.uiCard.model.DeduplicateNamesForModels([newModel])
        else:
            newModel.SetProperty("name", newModel.DeduplicateName("card_1",
                [m.GetProperty("name") for m in self.stackManager.stackModel.childModels]), notify=False)
        return newModel

    def GetType(self):
        return self.type

    def GetDisplayType(self):
        displayTypes = {"card": "Card",
                        "button": "Button",
                        "textfield": "TextField",
                        "textlabel": "TextLabel",
                        "image": "Image",
                        "pen": "Pen",
                        "line": "Line",
                        "rect": "Rectangle",
                        "oval": "Oval",
                        "poly": "Polygon",
                        "roundrect": "Round Rectangle",
                        "group": "Group"}
        return displayTypes[self.type]

    def SetDirty(self, isDirty):
        if isDirty:
            self.isDirty = True
        else:
            self.isDirty = False
            for child in self.childModels:
                child.SetDirty(False)

    def GetDirty(self):
        if self.isDirty:
            return True
        for card in self.childModels:
            if card.GetDirty():
                return True
        return False

    def GetPath(self):
        parts = []
        m = self
        while m.parent:
            parts.append(m.GetProperty("name"))
            m = m.parent
        return ".".join(reversed(parts))

    def SetStackManager(self, stackManager):
        self.stackManager = stackManager
        for m in self.childModels:
            m.SetStackManager(stackManager)

    def GetAbsolutePosition(self):
        p = self.GetProperty("position")
        pos = wx.RealPoint(p[0], p[1])  # Copy so we don't edit the model's position
        parent = self.parent
        while parent and parent.type != "card":
            parentPos = parent.GetProperty("position")
            pos += parentPos
            parent = parent.parent
        return pos

    def SetAbsolutePosition(self, pos):
        parent = self.parent
        pos = wx.RealPoint(pos[0], pos[1])
        while parent and parent.type != "card":
            parentPos = parent.GetProperty("position")
            pos -= parentPos
            parent = parent.parent
        self.SetProperty("position", pos)

    def IsHidden(self):
        """ Returns True iff this object or any of its ancestors has its hidden property set to True """
        if self.properties["hidden"]:
            return True
        if self.parent:
            return self.parent.IsHidden()
        return False

    def GetCenter(self):
        return self.GetProperty("center")

    def SetCenter(self, center):
        self.SetProperty("center", center)

    def GetFrame(self):
        p = wx.Point(self.GetProperty("position"))
        s = self.GetProperty("size")
        return wx.Rect(p, s)

    def GetAbsoluteFrame(self):
        p = wx.Point(self.GetAbsolutePosition())
        s = self.GetProperty("size")
        return wx.Rect(p, s)

    def SetFrame(self, rect):
        self.SetProperty("position", rect.Position)
        self.SetProperty("size", rect.Size)

    def GetData(self):
        handlers = {}
        for k, v in self.handlers.items():
            if len(v.strip()) > 0:
                handlers[k] = v

        props = self.properties.copy()
        props.pop("hidden")
        props.pop("speed")
        for k,v in self.propertyTypes.items():
            if v in ["point", "floatpoint", "size"] and k in props:
                props[k] = list(props[k])
            elif v == "dict":
                props[k] = self.SanitizeDict(props[k], [])

        if len(props["data"]) == 0:
            props.pop("data")

        return {"type": self.type,
                "handlers": handlers,
                "properties": props}

    # These Sanitize* methods make sure that the "data" property only includes json-serializable data
    def SanitizeKey(self, val, seen):
        if type(val) == dict:
            value = None
        else:
            value = self.SanitizeValue(val, seen)
        return value

    def SanitizeValue(self, val, seen):
        if type(val) in [bool, int, float, str, None]:
            value = val
        elif isinstance(val, (wx.Point, wx.RealPoint, wx.Size, CDSPoint, CDSRealPoint, CDSSize)):
            value = self.SanitizeList(list(val), seen)
        elif type(val) == dict:
            if val not in seen:
                value = self.SanitizeDict(val, seen)
            else:
                value = None
        elif type(val) in [list, set, tuple]:
            if val not in seen:
                value = self.SanitizeList(list(val), seen)
            else:
                value = None
        else:
            try:
                value = str(val)
            except (ValueError, TypeError) as e:
                value = None
        return value

    def SanitizeDict(self, inDict, seen):
        seen.append(inDict)
        outDict = {}
        for k,v in inDict.items():
            key = self.SanitizeKey(k, seen)
            value = self.SanitizeValue(v, seen)
            if key is not None and value is not None:
                outDict[key] = value
        return outDict

    def SanitizeList(self, inList, seen):
        seen.append(inList)
        outList = []
        for v in inList:
            value = self.SanitizeValue(v, seen)
            if value is not None:
                outList.append(value)
        return outList

    def SetData(self, data):
        for k, v in data["handlers"].items():
            self.handlers[k] = v
        for k, v in data["properties"].items():
            if k in self.propertyTypes:
                if self.propertyTypes[k] == "point":
                    self.SetProperty(k, wx.Point(v), notify=False)
                elif self.propertyTypes[k] == "floatpoint":
                    self.SetProperty(k, wx.RealPoint(v[0], v[1]), notify=False)
                elif self.propertyTypes[k] == "size":
                    self.SetProperty(k, wx.Size(v), notify=False)
                else:
                    self.SetProperty(k, v, notify=False)

    def SetFromModel(self, model):
        for k, v in model.handlers.items():
            self.handlers[k] = v
        for k, v in model.properties.items():
            if self.propertyTypes[k] == "point":
                self.SetProperty(k, wx.Point(v), notify=False)
            elif self.propertyTypes[k] == "floatpoint":
                self.SetProperty(k, wx.RealPoint(v[0], v[1]), notify=False)
            elif self.propertyTypes[k] == "size":
                self.SetProperty(k, wx.Size(v), notify=False)
            else:
                self.SetProperty(k, v, notify=False)

    # Custom property order and mask for the inspector
    def PropertyKeys(self):
        if self.parent and self.parent.type == 'group':
            keys = self.propertyKeys.copy()
            keys.remove('position')
            keys.remove('size')
            return keys
        return self.propertyKeys

    # Options currently are string, bool, int, float, point, floatpoint, size, choice, color, file
    def GetPropertyType(self, key):
        return self.propertyTypes[key]

    def GetPropertyChoices(self, key):
        return self.propertyChoices[key]

    def GetProperty(self, key):
        if key == "center":
            p = self.GetAbsolutePosition()
            s = self.GetProperty("size")
            center = [p.x + s.width / 2, p.y + s.height / 2]
            return center
        elif key in self.properties:
            return self.properties[key]
        return None

    def GetHandler(self, key):
        if key in self.handlers:
            return self.handlers[key]
        return None

    def GetChildModelByName(self, name):
        if self.properties["name"] == name:
            return self
        for child in self.childModels:
            result = child.GetChildModelByName(name)
            if result:
                return result
        return None

    def GetCard(self):
        if self.type == 'stack':
            return None
        if self.type == "card":
            return self
        if not self.parent:
            return None

        m = self
        while m.parent and m.type != 'card':
            m = m.parent
        return m

    def GetProperties(self):
        return self.properties

    def GetHandlers(self):
        return self.handlers

    def PerformFlips(self, fx, fy, notify=True):
        pass

    def OrderMoveTo(self, index):
        index = index % len(self.parent.childModels) # Convert negative index to positive
        if index < 0 or index > len(self.parent.childModels)-1:
            return
        self.parent.childModels.remove(self)
        self.parent.childModels.insert(index, self)
        if self.GetCard() == self.stackManager.uiCard.model:
            self.stackManager.LoadCardAtIndex(self.stackManager.cardIndex, reload=True)

    def OrderMoveBy(self, delta):
        index = self.parent.childModels.index(self) + delta
        self.OrderMoveTo(index)

    def FramePartChanged(self, cdsFramePart):
        if cdsFramePart.role == "position":
            self.SetAbsolutePosition(cdsFramePart)
        elif cdsFramePart.role == "size":
            self.SetProperty("size", cdsFramePart)
        elif cdsFramePart.role == "center":
            self.SetCenter(cdsFramePart)
        elif cdsFramePart.role == "speed":
            self.SetProperty("speed", cdsFramePart)

    def Notify(self, key):
        if self.stackManager:
            self.stackManager.OnPropertyChanged(self, key)

    def SetProperty(self, key, value, notify=True):
        if self.didSetDown: return
        if key in self.propertyTypes and self.propertyTypes[key] == "point" and not isinstance(value, wx.Point):
            value = wx.Point(value)
        elif key in self.propertyTypes and self.propertyTypes[key] == "floatpoint" and not isinstance(value, wx.RealPoint):
            value = wx.RealPoint(value[0], value[1])
        elif key in self.propertyTypes and self.propertyTypes[key] == "size" and not isinstance(value, wx.Point):
            value = wx.Size(value)
        elif key in self.propertyTypes and self.propertyTypes[key] == "choice" and value not in self.propertyChoices[key]:
            return
        elif key in self.propertyTypes and self.propertyTypes[key] == "color" and isinstance(value, wx.Colour):
            value = value.GetAsString(flags=wx.C2S_HTML_SYNTAX)

        if key == "name":
            value = re.sub(r'\W+', '', value)
            if not re.match(r'[A-Za-z][A-Za-z_0-9]*', value):
                if notify:
                    self.Notify(key)
                return
        elif key == "size":
            if value.width < self.minSize.width: value.width = self.minSize.width
            if value.height < self.minSize.height: value.height = self.minSize.height
        elif key == "center":
            s = self.GetProperty("size")
            self.SetAbsolutePosition([value.x - s.width / 2, value.y - s.height / 2])
            return

        if self.properties[key] != value:
            self.properties[key] = value
            if notify:
                self.Notify(key)
            self.isDirty = True

    def InterpretPropertyFromString(self, key, valStr):
        propType = self.propertyTypes[key]
        val = valStr
        try:
            if propType == "bool":
                val = valStr == "True"
            elif propType == "int":
                val = int(valStr)
            elif propType == "float":
                val = float(valStr)
            elif propType in ["point", "floatpoint"]:
                val = ast.literal_eval(valStr)
                if not isinstance(val, (list, tuple)) or len(val) != 2:
                    raise Exception()
            elif propType == "size":
                val = ast.literal_eval(valStr)
                if not isinstance(val, (list, tuple)) or len(val) != 2:
                    raise Exception()
        except:
            return None
        return val

    def SetHandler(self, key, value):
        if self.handlers[key] != value:
            self.handlers[key] = value
            self.isDirty = True

    def AddAnimation(self, key, duration, onUpdate, onStart=None, onFinish=None, onCancel=None):
        # On Runner thread
        if self.didSetDown: return
        animDict = {"duration": duration,
                    "onStart": onStart,
                    "onUpdate": onUpdate,
                    "onFinish": onFinish,
                    "onCancel": onCancel
                    }
        with self.animLock:
            if key not in self.animations:
                self.animations[key] = [animDict]
                self.StartAnimation(key)
            else:
                self.animations[key].append(animDict)

    def StartAnimation(self, key):
        # On Runner or Main thread
        if key in self.animations:
            animDict = self.animations[key][0]
            if "startTime" not in animDict:
                animDict["startTime"] = time()
                if animDict["onStart"]:
                    animDict["onStart"](animDict)

    def FinishAnimation(self, key):
        # On Main thread
        with self.animLock:
            if key in self.animations:
                animList = self.animations[key]
                animDict = animList[0]
                if len(animList) > 1:
                    del animList[0]
                    self.StartAnimation(key)
                else:
                    del self.animations[key]
                if "startTime" in animDict and animDict["onFinish"]:
                    animDict["onFinish"](animDict)

    def StopAnimation(self, key=None):
        # On Runner thread
        if key:
            # Stop animating this one property
            with self.animLock:
                if key in self.animations:
                    animDict = self.animations[key][0]
                    if "startTime" in animDict and animDict["onCancel"]:
                        animDict["onCancel"](animDict)
                    del self.animations[key]
            return

        # Stop animating all properties
        with self.animLock:
            for (key, animList) in self.animations.items():
                animDict = animList[0]
                if "startTime" in animDict and animDict["onCancel"]:
                    animDict["onCancel"](animDict)
            self.animations = {}

    def DeduplicateName(self, name, existingNames):
        existingNames.extend(self.reservedNames) # disallow globals
        if name in existingNames:
            name = name.rstrip("0123456789_")
            name = self.GetNextAvailableName(name, existingNames)
        return name

    def GetNextAvailableName(self, base, existingNames):
        i = 0
        if base[-1] != "_":
            base += "_"
        while True:
            i += 1
            name = base+str(i)
            if name not in existingNames:
                return name

    def GetProxy(self):
        if not self.proxy:
            self.proxy = self.proxyClass(self)
        return self.proxy

    def RunSetup(self, runner):
        if self.type == "card":
            runner.SetupForCard(self)
        if self.GetHandler("OnSetup"):
            runner.RunHandler(self, "OnSetup", None)
        for m in self.childModels:
            m.RunSetup(runner)


class ViewProxy(object):
    """
    This class and its subclasses are the user-accessible objects exposed to event handler code.
    They purposefully contain no attributes for users to avoid, except a single _model reference.
    """

    def __init__(self, model):
        super().__init__()
        self._model = model

    def __getattr__(self, item):
        model = self._model
        if model:
            for m in model.childModels:
                if m.properties["name"] == item:
                    return m.GetProxy()
        return super().__getattribute__(item)

    def SendMessage(self, message):
        if not isinstance(message, str):
            raise TypeError("message must be a string")

        model = self._model
        if not model: return

        if model.stackManager.runner:
           model.stackManager.runner.RunHandler(model, "OnMessage", None, message)

    def Focus(self):
        model = self._model
        if not model: return

        if model.stackManager.runner:
            model.stackManager.runner.SetFocus(self)

    @property
    @RunOnMain
    def hasFocus(self):
        model = self._model
        if not model: return False

        uiView = model.stackManager.GetUiViewByModel(model)
        if uiView and uiView.view:
            return uiView.view.HasFocus()

    def Clone(self, **kwargs):
        model = self._model
        if not model: return None

        if model.type != "card":
            # update the model immediately on the runner thread
            newModel = model.CreateCopy()
            newModel.SetProperty("speed", model.GetProperty("speed"), notify=False)
            if not self.visible:
                newModel.SetProperty("hidden", True, notify=False)
            for k,v in kwargs.items():
                if k in newModel.propertyTypes:
                    newModel.SetProperty(k, v, notify=False)

            model.GetCard().AddChild(newModel)
            newModel.RunSetup(model.stackManager.runner)
            if newModel.GetCard() != model.stackManager.uiCard.model:
                model.stackManager.runner.SetupForCard(model.stackManager.uiCard.model)

            @RunOnMainAsync
            def func():
                if not newModel.didSetDown:
                    # add the view on the main thread
                    newModel.stackManager.AddUiViewsFromModels([newModel], False)
            func()
        else:
            @RunOnMain
            def func():
                # When cloning a card, update the model and view together in a rare synchronous call to the main thread
                newModel = model.stackManager.DuplicateCard()

                if "center" in kwargs and "size" in kwargs:
                    newModel.SetProperty("size", kwargs["size"])
                    newModel.SetProperty("center", kwargs["center"])
                    kwargs.pop("size")
                    kwargs.pop("center")

                for k,v in kwargs.items():
                    if k in newModel.propertyTypes:
                        newModel.SetProperty(k, v)
                return newModel
            newModel = func()

        return newModel.GetProxy()

    def Delete(self):
        model = self._model
        if not model or not model.parent or model.parent.type == "group":
            return

        # immediately update the model
        sm = model.stackManager
        if model.type != "card":
            model.parent.RemoveChild(model)

        @RunOnMainAsync
        def func():
            if model.type != "card":
                # update views on the main thread
                sm.RemoveUiViewByModel(model)
            else:
                # When cloning a card, update the model and view together in a rare synchronous call to the main thread
                sm.RemoveCardRaw(model)
        func()

    @RunOnMain
    def Cut(self):
        # update the model and view together in a rare synchronous call to the main thread
        model = self._model
        if not model: return

        model.stackManager.CutModels([model], False)

    @RunOnMain
    def Copy(self):
        # update the model and view together in a rare synchronous call to the main thread
        model = self._model
        if not model: return

        model.stackManager.CopyModels([model])

    # Paste is in the runner

    @property
    def name(self):
        model = self._model
        if not model: return ""
        return model.GetProperty("name")

    @property
    def type(self):
        model = self._model
        if not model: return None
        return model.type

    @property
    def data(self):
        model = self._model
        if not model: return {}
        return model.GetProperty("data")

    @property
    def parent(self):
        model = self._model
        if not model: return None
        parent = model.parent
        if parent: parent = parent.GetProxy()
        return parent

    @property
    def children(self):
        model = self._model
        if not model: return []
        return [m.GetProxy() for m in model.childModels]

    @property
    def size(self):
        model = self._model
        if not model: return wx.Size(0,0)
        return CDSSize(model.GetProperty("size"), model=model, role="size")
    @size.setter
    def size(self, val):
        try:
            val = wx.Size(val[0], val[1])
        except:
            raise ValueError("size must be a size or a list of two numbers")
        model = self._model
        if not model: return
        model.SetProperty("size", val)

    @property
    def position(self):
        model = self._model
        if not model: return wx.Point(0,0)
        return CDSRealPoint(model.GetAbsolutePosition(), model=model, role="position")
    @position.setter
    def position(self, val):
        try:
            val = wx.RealPoint(val[0], val[1])
        except:
            raise ValueError("position must be a point or a list of two numbers")
        model = self._model
        if not model: return
        model.SetAbsolutePosition(val)

    @property
    def speed(self):
        model = self._model
        if not model: return wx.Point(0,0)
        speed = CDSPoint(model.GetProperty("speed"), model=model, role="speed")
        return speed
    @speed.setter
    def speed(self, val):
        try:
            val = wx.RealPoint(val[0], val[1])
        except:
            raise ValueError("speed must be a point or a list of two numbers")
        model = self._model
        if not model: return
        model.SetProperty("speed", val)

    @property
    def center(self):
        model = self._model
        if not model: return wx.Point(0,0)
        return CDSRealPoint(model.GetCenter(), model=model, role="center")
    @center.setter
    def center(self, center):
        try:
            center = wx.RealPoint(center[0], center[1])
        except:
            raise ValueError("center must be a point or a list of two numbers")
        model = self._model
        if not model: return
        model.SetCenter(center)

    @RunOnMainAsync
    def FlipHorizontal(self):
        model = self._model
        if not model: return
        model.PerformFlips(True, False)

    @RunOnMainAsync
    def FlipVertical(self):
        model = self._model
        if not model: return
        model.PerformFlips(False, True)

    @RunOnMainAsync
    def OrderToFront(self):
        model = self._model
        if not model: return
        model.OrderMoveTo(-1)

    @RunOnMainAsync
    def OrderForward(self):
        model = self._model
        if not model: return
        model.OrderMoveBy(1)

    @RunOnMainAsync
    def OrderBackward(self):
        model = self._model
        if not model: return
        model.OrderMoveBy(-1)

    @RunOnMainAsync
    def OrderToBack(self):
        model = self._model
        if not model: return
        model.OrderMoveTo(0)

    def OrderToIndex(self, i):
        if not isinstance(i, int):
            raise TypeError("i must be a number")

        model = self._model
        if not model: return

        @RunOnMainAsync
        def f():
            if model.didSetDown: return
            model.OrderMoveTo(i)
        f()

    def Show(self):
        self.visible = True
    def Hide(self):
        self.visible = False

    @property
    def visible(self):
        model = self._model
        if not model: return False
        return not model.IsHidden()
    @visible.setter
    def visible(self, val):
        model = self._model
        if not model: return
        model.SetProperty("hidden", not bool(val))

    @property
    def eventHandlers(self):
        model = self._model
        if not model: return {}
        return model.handlers

    def IsTouchingPoint(self, point):
        if not isinstance(point, (wx.Point, wx.RealPoint, CDSPoint, CDSRealPoint, list, tuple)):
            raise TypeError("point needs to be a point or a list of two numbers")
        if len(point) != 2:
            raise TypeError("point needs to be a point or a list of two numbers")
        try:
            int(point[0]), int(point[1])
        except:
            raise ValueError("point needs to be a point or a list of two numbers")

        model = self._model
        if not model: return False

        @RunOnMain
        def f():
            if model.didSetDown: return False
            s = model.stackManager.GetUiViewByModel(model)
            if not s:
                return False
            sreg = s.GetHitRegion()
            sreg = wx.Region(sreg)
            sreg.Offset(*model.GetProperty("position"))
            return sreg.Contains(wx.Point(point)) == wx.InRegion
        return f()

    def IsTouching(self, obj):
        if not isinstance(obj, ViewProxy):
            raise TypeError("obj must be a CardStock object")

        model = self._model
        oModel = obj._model
        if not model or not oModel: return False

        @RunOnMain
        def f():
            if model.didSetDown: return False
            s = model.stackManager.GetUiViewByModel(model)
            o = model.stackManager.GetUiViewByModel(oModel)
            if not s or not o:
                return False
            sreg = s.GetHitRegion()
            oreg = o.GetHitRegion()
            sreg = wx.Region(sreg)
            oreg = wx.Region(oreg)
            sreg.Offset(*model.GetProperty("position"))
            oreg.Offset(*oModel.GetProperty("position"))
            sreg.Intersect(oreg)
            return not sreg.IsEmpty()
        return f()

    def IsTouchingEdge(self, obj):
        if not isinstance(obj, ViewProxy):
            raise TypeError("obj must be a CardStock object")

        model = self._model
        oModel = obj._model
        if not model or not oModel: return None

        @RunOnMain
        def f():
            if model.didSetDown: return None
            sf = model.GetAbsoluteFrame() # self frame in card coords
            f = oModel.GetAbsoluteFrame() # other frame in card coords
            top = wx.Rect(f.Left, f.Top, f.Width, 1)
            bottom = wx.Rect(f.Left, f.Bottom, f.Width, 1)
            left = wx.Rect(f.Left, f.Top, 1, f.Height)
            right = wx.Rect(f.Right, f.Top, 1, f.Height)
            if sf.Intersects(top): return "Top"
            if sf.Intersects(bottom): return "Bottom"
            if sf.Intersects(left): return "Left"
            if sf.Intersects(right): return "Right"
            return None
        return f()

    def AnimatePosition(self, duration, endPosition, onFinished=None, *args, **kwargs):
        if not (isinstance(duration, int) or isinstance(duration, float)):
            raise TypeError("duration must be a number")
        try:
            endPosition = wx.RealPoint(endPosition)
        except:
            raise ValueError("endPosition must be a point or a list of two numbers")

        model = self._model
        if not model: return

        def onStart(animDict):
            origPosition = model.GetAbsolutePosition()
            offsetPt = endPosition - origPosition
            offset = wx.RealPoint(offsetPt[0], offsetPt[1])
            animDict["origPosition"] = origPosition
            animDict["offset"] = offset
            model.SetProperty("speed", offset*(1.0/duration))

        def onUpdate(progress, animDict):
            model.SetAbsolutePosition(animDict["origPosition"] + animDict["offset"] * progress)

        def internalOnFinished(animDict):
            model.SetProperty("speed", (0,0), notify=False)
            if onFinished: self._model.stackManager.runner.EnqueueFunction(onFinished, *args, **kwargs)

        def onCanceled(animDict):
            model.SetProperty("speed", (0,0))

        model.AddAnimation("position", duration, onUpdate, onStart, internalOnFinished, onCanceled)

    def AnimateCenter(self, duration, endCenter, onFinished=None, *args, **kwargs):
        if not (isinstance(duration, int) or isinstance(duration, float)):
            raise TypeError("duration must be a number")
        try:
            endCenter = wx.RealPoint(endCenter)
        except:
            raise ValueError("endCenter must be a point or a list of two numbers")

        model = self._model
        if not model: return

        def onStart(animDict):
            origCenter = model.GetCenter()
            offsetPt = endCenter - origCenter
            offset = wx.RealPoint(offsetPt[0], offsetPt[1])
            animDict["origCenter"] = origCenter
            animDict["offset"] = offset
            self._model.SetProperty("speed", offset*(1.0/duration))

        def onUpdate(progress, animDict):
            model.SetCenter(animDict["origCenter"] + animDict["offset"] * progress)

        def internalOnFinished(animDict):
            model.SetProperty("speed", (0,0), notify=False)
            if onFinished: self._model.stackManager.runner.EnqueueFunction(onFinished, *args, **kwargs)

        def onCanceled(animDict):
            model.SetProperty("speed", (0,0))

        model.AddAnimation("position", duration, onUpdate, onStart, internalOnFinished, onCanceled)

    def AnimateSize(self, duration, endSize, onFinished=None, *args, **kwargs):
        if not (isinstance(duration, int) or isinstance(duration, float)):
            raise TypeError("duration must be a number")
        try:
            endSize = wx.Size(endSize)
        except:
            raise ValueError("endSize must be a size or a list of two numbers")

        model = self._model
        if not model: return

        def onStart(animDict):
            origSize = model.GetProperty("size")
            offset = wx.Size(endSize-origSize)
            animDict["origSize"] = origSize
            animDict["offset"] = offset

        def onUpdate(progress, animDict):
            model.SetProperty("size", animDict["origSize"] + animDict["offset"] * progress)

        def internalOnFinished(animDict):
            if onFinished: self._model.stackManager.runner.EnqueueFunction(onFinished, *args, **kwargs)

        model.AddAnimation("size", duration, onUpdate, onStart, internalOnFinished)

    def StopAnimating(self, propertyName=None):
        model = self._model
        if not model: return
        model.StopAnimation(propertyName)
