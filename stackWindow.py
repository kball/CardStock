#!/usr/bin/python
# stackWindow.py

"""
This module contains the StackWindow class which is a window that you
can do simple drawings upon. and add Buttons and TextFields to.
"""


import wx
from wx.lib.docview import CommandProcessor
import json
from tools import *
from commands import *
from stackModel import StackModel
from uiCard import UiCard, CardModel
from uiButton import UiButton
from uiTextField import UiTextField
from uiTextLabel import UiTextLabel
from uiImage import UiImage
from uiShapes import UiShapes

# ----------------------------------------------------------------------

class StackWindow(wx.Window):
    def __init__(self, parent, ID, stackModel):
        wx.Window.__init__(self, parent, ID, style=wx.WANTS_CHARS)
        self.listeners = []
        self.designer = None
        self.isEditing = False  # Is in Editing mode (running from the designer), as opposed to just the viewer
        self.command_processor = CommandProcessor()
        self.noIdling = False
        self.timer = None
        self.tool = None
        self.cacheView = wx.Window(self, size=(0,0))  # just an offscreen holder for cached uiView.views
        self.cacheView.Hide()
        self.uiViewCache = {}
        self.globalCursor = None
        self.lastMousePos = wx.Point(0,0)

        if not stackModel:
            stackModel = StackModel()
            stackModel.AppendCardModel(CardModel())

        self.stackModel = stackModel
        self.selectedView = None
        self.uiViews = []
        self.cardIndex = None
        self.uiCard = UiCard(self, stackModel.cardModels[0])
        self.LoadCardAtIndex(0)
        stackModel.AddPropertyListener(self.OnPropertyChanged)

        self.uiCard.model.SetDirty(False)
        self.command_processor.ClearCommands()

        # When the window is destroyed, clean up resources.
        self.Bind(wx.EVT_WINDOW_DESTROY, self.Cleanup)

    def Cleanup(self, evt):
        if evt.GetEventObject() == self:
            if hasattr(self, "menu"):
                self.menu.Destroy()
                del self.menu
            if self.timer:
                self.timer.Stop()

    def RefreshNow(self):
        self.Refresh()
        self.Update()
        self.noIdling = True
        wx.GetApp().Yield()
        self.noIdling = False

    def SetEditing(self, editing):
        self.isEditing = editing
        if not editing:
            self.SelectUiView(None)
            self.timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self.OnIdleTimer, self.timer)
            self.timer.Start(33)
        else:
            if self.timer:
                self.timer.Stop()

    def UpdateCursor(self):
        if self.tool:
            self.globalCursor = self.tool.GetCursor()
        else:
            self.globalCursor = None

        if self.globalCursor:
            self.SetCursor(wx.Cursor(self.globalCursor))
            for uiView in self.uiViews:
                uiView.view.SetCursor(wx.Cursor(self.globalCursor))
        else:
            cursor = wx.CURSOR_ARROW
            self.SetCursor(wx.Cursor(cursor))
            for uiView in self.uiViews:
                viewCursor = uiView.GetCursor()
                uiView.view.SetCursor(wx.Cursor(viewCursor if viewCursor else cursor))

    def OnIdleTimer(self, event):
        if not self.isEditing and not self.noIdling:
            self.uiCard.OnIdle(event)

    def SetTool(self, tool):
        self.tool = tool
        self.UpdateCursor()

    def ClearAllViews(self):
        self.SelectUiView(None)
        for ui in self.uiViews.copy():
            if ui.model.type != "card":
                ui.model.RemovePropertyListener(self.OnPropertyChanged)
                self.uiViews.remove(ui)
                ui.view.Reparent(self.cacheView)
                self.uiViewCache[ui.model] = ui

    def CreateViews(self, cardModel):
        self.uiCard.SetModel(cardModel)
        self.uiViews = []
        for m in cardModel.childModels:
            self.AddUiViewFromModel(m, canUndo=False)  # Don't allow undoing card loads

    def SetStackModel(self, model):
        if self.stackModel:
            self.stackModel.RemovePropertyListener(self.OnPropertyChanged)
        self.ClearAllViews()
        self.stackModel = model
        model.AddPropertyListener(self.OnPropertyChanged)
        self.cardIndex = None
        self.LoadCardAtIndex(0)
        self.SetSize(self.stackModel.GetProperty("size"))
        self.command_processor.ClearCommands()
        self.stackModel.SetDirty(False)
        self.UpdateCursor()

    def LoadCardAtIndex(self, index, reload=False):
        if index != self.cardIndex or reload == True:
            if not self.isEditing and self.cardIndex is not None and not reload:
                oldCardModel = self.stackModel.cardModels[self.cardIndex]
                if oldCardModel.runner:
                    oldCardModel.runner.RunHandler(oldCardModel, "OnHideCard", None)
            self.cardIndex = index
            self.ClearAllViews()
            if index is not None:
                cardModel = self.stackModel.GetCardModel(index)
                self.CreateViews(cardModel)
                self.SelectUiView(self.uiCard)
                cardModel.AddPropertyListener(self.OnPropertyChanged)
                self.Refresh()
                self.Update()
                if self.designer:
                    self.designer.UpdateCardList()
                if not self.isEditing and self.uiCard.model.runner:
                    self.uiCard.model.runner.SetupForCurrentCard()
                    self.uiCard.model.runner.RunHandler(self.uiCard.model, "OnShowCard", None)
                self.noIdling = True
                wx.GetApp().Yield()
                self.noIdling = False

    def SetDesigner(self, designer):
        self.designer = designer

    def CopyView(self):
        clipData = wx.CustomDataObject("org.cardstock.models")
        list = [self.selectedView.model.GetData()]
        data = bytes(json.dumps(list).encode('utf8'))
        clipData.SetData(data)
        wx.TheClipboard.Open()
        wx.TheClipboard.SetData(clipData)
        wx.TheClipboard.Close()

    def CutView(self):
        self.CopyView()
        if self.selectedView != self.uiCard:
            command = RemoveUiViewCommand(True, "Cut", self, self.cardIndex, self.selectedView.model)
            self.command_processor.Submit(command)
        else:
            self.RemoveCard()

    def PasteView(self):
        if not wx.TheClipboard.IsOpened():  # may crash, otherwise
            if wx.TheClipboard.Open():
                if wx.TheClipboard.IsSupported(wx.DataFormat("org.cardstock.models")):
                    clipData = wx.CustomDataObject("org.cardstock.models")
                    if wx.TheClipboard.GetData(clipData):
                        rawdata = clipData.GetData()
                        list = json.loads(rawdata.tobytes().decode('utf8'))
                        uiView = None
                        for dict in list:
                            model = CardModel.ModelFromData(dict)
                            if model.type == "card":
                                model.SetProperty("name", model.DeduplicateName(model.GetProperty("name"),
                                                                                [m.GetProperty("name") for m in
                                                                                 self.stackModel.cardModels]))
                                command = AddUiViewCommand(True, "Paste Card", self, self.cardIndex + 1, "card", model)
                                self.command_processor.Submit(command)
                            else:
                                uiView = self.AddUiViewFromModel(model)
                        if uiView:
                            self.SelectUiView(uiView)
                wx.TheClipboard.Close()

    def AddUiViewInternal(self, type, model=None):
        uiView = None

        if model and model in self.uiViewCache:
            uiView = self.uiViewCache.pop(model)
            uiView.view.Reparent(self)
        else:
            if type == "button":
                uiView = UiButton(self, model)
            elif type == "textfield" or type == "field":
                uiView = UiTextField(self, model)
            elif type == "textlabel" or type == "label":
                uiView = UiTextLabel(self, model)
            elif type == "image":
                uiView = UiImage(self, model)
            elif type == "shapes":
                uiView = UiShapes(self, model)

        if uiView:
            if not model:
                uiView.view.Center()
                uiView.model.SetProperty("position", uiView.view.GetPosition())
                uiView.model.SetProperty("size", uiView.view.GetSize())
            self.uiViews.append(uiView)
            if not uiView.model in self.uiCard.model.childModels:
                self.uiCard.model.AddChild(uiView.model)
            uiView.model.AddPropertyListener(self.OnPropertyChanged)

            if self.globalCursor:
                uiView.view.SetCursor(wx.Cursor(self.globalCursor))
        return uiView

    def AddUiViewFromModel(self, model, canUndo=True):
        uiView = None

        if not model in self.uiCard.model.childModels:
            model.SetProperty("name", self.uiCard.model.DeduplicateNameInCard(model.GetProperty("name")))

        command = None
        if model.GetType() == "button":
            command = AddUiViewCommand(True, 'Add Button', self, self.cardIndex, "button", model)
        elif model.GetType() == "textfield":
            command = AddUiViewCommand(True, 'Add TextField', self, self.cardIndex, "textfield", model)
        elif model.GetType() == "textlabel":
            command = AddUiViewCommand(True, 'Add TextLabel', self, self.cardIndex, "textlabel", model)
        elif model.GetType() == "image":
            command = AddUiViewCommand(True, 'Add Image', self, self.cardIndex, "image", model)
        elif model.GetType() == "shapes":
            command = AddUiViewCommand(True, 'Add Shape', self, self.cardIndex, "shapes", model)

        if canUndo:
            self.command_processor.Submit(command)
        else:
            # Don't mess with the Undo queue when we're just building a pgae
            command.Do()

        uiView = self.uiViews[-1]

        if self.globalCursor:
            uiView.view.SetCursor(wx.Cursor(self.globalCursor))

        return uiView

    def GetSelectedUiView(self):
        return self.selectedView

    def SelectUiView(self, view):
        if self.isEditing:
            if self.selectedView:
                self.selectedView.SetSelected(False)
            if view:
                view.SetSelected(True)
            self.selectedView = view
            if self.designer:
                self.designer.SetSelectedUiView(view)

    def OnPropertyChanged(self, model, key):
        if model == self.stackModel:
            uiView = self.uiCard
            if key == "size":
                self.SetSize(model.GetProperty(key))
        else:
            uiView = self.GetUiViewByModel(model)
        if self.designer:
            self.designer.cPanel.UpdatedProperty(uiView, key)

    def UpdateSelectedUiView(self):
        if self.designer:
            self.designer.UpdateSelectedUiView()

    def GetUiViewByModel(self, model):
        for ui in self.uiViews:
            if ui.model == model:
                return ui
        return None

    def RemoveUiViewByModel(self, viewModel):
        for ui in self.uiViews.copy():
            if ui.model == viewModel:
                if self.selectedView == ui:
                    self.SelectUiView(self.uiCard)
                ui.model.RemovePropertyListener(self.OnPropertyChanged)
                self.uiViews.remove(ui)
                self.uiCard.model.RemoveChild(ui.model)
                ui.DestroyView()
                return

    def ReorderSelectedView(self, direction):
        if self.selectedView and self.selectedView != self.uiCard:
            currentIndex = self.uiCard.model.childModels.index(self.selectedView.model)
            newIndex = None
            if direction == "end": newIndex = 0
            elif direction == "fwd": newIndex = currentIndex+1
            elif direction == "back": newIndex = currentIndex-1
            elif direction == "front": newIndex = len(self.uiCard.model.childModels)-1

            if newIndex < 0: newIndex = 0
            if newIndex >= len(self.uiCard.model.childModels): newIndex = len(self.uiCard.model.childModels)-1

            if newIndex != currentIndex:
                command = ReorderUiViewCommand(True, "Reorder View", self, self.cardIndex, self.selectedView.model, newIndex)
                self.command_processor.Submit(command)

    def ReorderCurrentCard(self, direction):
        currentIndex = self.cardIndex
        newIndex = None
        if direction == "fwd": newIndex = currentIndex + 1
        elif direction == "back": newIndex = currentIndex - 1

        if newIndex < 0: newIndex = 0
        if newIndex >= len(self.stackModel.cardModels): newIndex = len(self.stackModel.cardModels) - 1

        if newIndex != currentIndex:
            command = ReorderUiViewCommand(True, "Reorder Card", self, self.cardIndex, self.stackModel.cardModels[currentIndex], newIndex)
            self.command_processor.Submit(command)

    def AddCard(self):
        newCard = CardModel()
        newCard.SetProperty("name", newCard.DeduplicateName("card_1",
                                                            [m.GetProperty("name") for m in self.stackModel.cardModels]))
        command = AddUiViewCommand(True, "Add Card", self, self.cardIndex+1, "card", newCard)
        self.command_processor.Submit(command)

    def DuplicateCard(self):
        newCard = CardModel()
        newCard.SetData(self.stackModel.cardModels[self.cardIndex].GetData())
        newCard.SetProperty("name", newCard.DeduplicateName(newCard.GetProperty("name"),
                                                            [m.GetProperty("name") for m in self.stackModel.cardModels]))
        command = AddUiViewCommand(True, "Duplicate Card", self, self.cardIndex+1, "card", newCard)
        self.command_processor.Submit(command)

    def RemoveCard(self):
        index = self.cardIndex
        if len(self.stackModel.cardModels) > 1:
            command = RemoveUiViewCommand(True, "Add Card", self, index, self.stackModel.cardModels[index])
            self.command_processor.Submit(command)

    def OnMouseDown(self, uiView, event):
        if self.tool and self.isEditing:
            self.tool.OnMouseDown(uiView, event)
        else:
            uiView.OnMouseDown(event)

    def OnMouseMove(self, uiView, event):
        pos = self.ScreenToClient(event.GetEventObject().ClientToScreen(event.GetPosition()))
        if pos == self.lastMousePos: return

        if self.tool and self.isEditing:
            self.tool.OnMouseMove(uiView, event)
        else:
            uiView.OnMouseMove(event)
            if uiView.model.type != "card":
                self.uiCard.OnMouseMove(event)
        self.lastMousePos = pos

    def OnMouseUp(self, uiView, event):
        if self.tool and self.isEditing:
            self.tool.OnMouseUp(uiView, event)
        else:
            uiView.OnMouseUp(event)

    def OnMouseEnter(self, uiView, event):
        if not self.isEditing:
            uiView.OnMouseEnter(event)

    def OnMouseExit(self, uiView, event):
        if not self.isEditing:
            uiView.OnMouseExit(event)

    def OnKeyDown(self, uiView, event):
        if self.tool and self.isEditing:
            ms = wx.GetMouseState()
            if event.GetKeyCode() == wx.WXK_ESCAPE and not ms.LeftIsDown():
                self.designer.cPanel.SetToolByName("hand")
            self.tool.OnKeyDown(uiView, event)
        else:
            self.uiCard.OnKeyDown(event)
            event.Skip()

    def OnKeyUp(self, uiView, event):
        if self.tool and self.isEditing:
            self.tool.OnKeyUp(uiView, event)
        else:
            self.uiCard.OnKeyUp(event)
            event.Skip()

    def Undo(self):
        self.command_processor.Undo()
        if not self.command_processor.CanUndo():
            self.stackModel.SetDirty(False)
        self.Refresh()

    def Redo(self):
        self.command_processor.Redo()
        self.Refresh()
