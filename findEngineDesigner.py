import wx
import stackManager
from uiView import ViewModel
from commands import SetPropertyCommand, SetHandlerCommand, CommandGroup
import re

SEARCHABLE_PROPERTIES = ["name", "text", "title", "file", "bgColor", "textColor", "penColor", "fillColor"]

"""
Find and Replace logic.
The search order is:
- Cards, first to last
  - Recursively find cardModel's childModels (obj1, obj2, obj2.child1, obj2.child2, obj3, etc.)
    - Property text, in model.PropertyKeys() order (this is display order in the inspector)
    - Handlers in model.handlers order (this is display order in the handlerPicker)
      - handler text, start to end

Create a dict of searchable item paths and values on every Find. Paths are of the form:
  - cardIndex.objectName.property.propertyName
  - cardIndex.objectName.handler.handlerName
Determine our currently selected findPath, and selection inside it, and start searching there.
Search each item in order, and call stackManager.ShowDesignerFindPath(findpath, selectionStart, selectionEnd) to show matches.

Only allow Replacing once per Find, to avoid duplicated replaceText.
"""

class FindEngine(object):
    def __init__(self, stackManager):
        super().__init__()
        self.stackManager = stackManager
        self.findData = wx.FindReplaceData(1)   # initializes and holds search parameters
        self.didReplace = False

    def AddDictItemsForModel(self, searchDict, i, model):
        for key in model.PropertyKeys():
            if key in SEARCHABLE_PROPERTIES:
                path = ".".join([str(i), model.GetProperty("name"), "property", key])
                searchDict[path] = model.GetProperty(key)
        for key, code in model.handlers.items():
            path = ".".join([str(i), model.GetProperty("name"), "handler", key])
            searchDict[path] = model.handlers[key]
        for m in model.childModels:
            self.AddDictItemsForModel(searchDict, i, m)

    def GenerateSearchDict(self):
        searchDict = {}
        i = 0
        for card in self.stackManager.stackModel.childModels:
            self.AddDictItemsForModel(searchDict, i, card)
            i += 1
        return searchDict

    def UpdateFindTextFromSelection(self):
        _, textSel = self.stackManager.GetDesignerFindPath()
        start, end, findStr = textSel
        if findStr and len(findStr):
            self.findData.SetFindString(findStr)

    def Find(self):
        findStr = self.findData.GetFindString()
        if len(findStr):
            searchDict = self.GenerateSearchDict()
            startPath, textSel = self.stackManager.GetDesignerFindPath()
            path, start, end = self.DoFindNext(searchDict, startPath, textSel)
            if path:
                self.didReplace = False
                self.stackManager.ShowDesignerFindPath(path, start, end)

    def Replace(self):
        if not self.didReplace:
            replaceStr = self.findData.GetReplaceString()
            findPath, textSel = self.stackManager.GetDesignerFindPath()
            command = self.DoReplaceAtPath(findPath, [textSel], replaceStr)
            if command:
                self.stackManager.command_processor.Submit(command)
            parts = findPath.split(".")
            key = parts[3]
            if parts[2] == "handler":
                self.stackManager.designer.cPanel.UpdateHandlerForUiViews([self.stackManager.designer.cPanel.lastSelectedUiView], key)
                pos = textSel[0] + len(replaceStr)
                self.stackManager.designer.cPanel.codeEditor.SetSelection(pos, pos)
                self.stackManager.designer.cPanel.codeEditor.ScrollRange(pos, pos)
            self.didReplace = True

    def DoFindNext(self, searchDict, startPath, textSel):
        flags = self.findData.GetFlags()
        findStr = self.findData.GetFindString()
        findBackwards = not (flags & 1)
        findWholeWord = flags & 2
        findMatchCase = flags & 4

        keyList = list(searchDict.keys())
        index = keyList.index(startPath)

        slicedKeys = keyList[index:]
        slicedKeys.extend(keyList[:index])
        slicedKeys.append(slicedKeys[0])
        if findBackwards:
            slicedKeys.reverse()

        for key in slicedKeys:
            text = searchDict[key]
            if len(text) == 0:
                textSel = None
                continue

            offset = 0
            if textSel and not findBackwards:
                text = text[textSel[1]:]
                offset = textSel[1]
            elif textSel:
                text = text[:textSel[0]]
            textSel = None

            flags = (re.MULTILINE) if (findMatchCase) else (re.IGNORECASE | re.MULTILINE)
            if findWholeWord:
                p = re.compile(r'\b{searchStr}\b'.format(searchStr=findStr), flags)
            else:
                p = re.compile(r'{searchStr}'.format(searchStr=findStr), flags)

            start = -1
            end = -1
            matches = [m for m in p.finditer(text)]
            if len(matches):
                if not findBackwards:
                    start = matches[0].start()
                    end = matches[0].end()
                else:
                    start = matches[-1].start()
                    end = matches[-1].end()

            if start != -1:
                return (key, start+offset, end+offset)
        return (None, None, None)

    def DoReplaceAtPath(self, findPath, textSels, replaceStr):
        parts = findPath.split(".")
        # cardIndex, objectName, property|handler, key
        cardIndex = int(parts[0])
        card = self.stackManager.stackModel.childModels[cardIndex]
        model = card.GetChildModelByName(parts[1])
        key = parts[3]
        command = None
        if parts[2] == "property":
            val = str(model.GetProperty(key))
            for textSel in reversed(textSels):
                val = val[:textSel[0]] + replaceStr + val[textSel[1]:]
            command = SetPropertyCommand(True, "Set Property", self.stackManager.designer.cPanel,
                                         cardIndex, model, key, val, False)
        elif parts[2] == "handler":
            val = model.handlers[key]
            for textSel in reversed(textSels):
                val = val[:textSel[0]] + replaceStr + val[textSel[1]:]
            command = SetHandlerCommand(True, "Set Handler", self.stackManager.designer.cPanel,
                                        cardIndex, model, key, val, None, None, False)
        return command

    def ReplaceAll(self):
        selectedUiViews = self.stackManager.GetSelectedUiViews()
        self.stackManager.SelectUiView(None)

        searchDict = self.GenerateSearchDict()
        findStr = self.findData.GetFindString()
        replaceStr = self.findData.GetReplaceString()
        flags = self.findData.GetFlags()
        findWholeWord = flags & 2
        findMatchCase = flags & 4

        commands = []

        for path, text in searchDict.items():
            if len(text) == 0:
                continue

            flags = (re.MULTILINE) if (findMatchCase) else (re.IGNORECASE | re.MULTILINE)
            if findWholeWord:
                p = re.compile(r'\b{searchStr}\b'.format(searchStr=findStr), flags)
            else:
                p = re.compile(r'{searchStr}'.format(searchStr=findStr), flags)

            matches = [m for m in p.finditer(text)]
            matchInfo = [(match.start(), match.end()) for match in matches]
            command = self.DoReplaceAtPath(path, matchInfo, replaceStr)
            commands.append(command)

        if len(commands):
            command = CommandGroup(True, "Replace All", commands)
            self.stackManager.command_processor.Submit(command)

        for ui in selectedUiViews:
            self.stackManager.SelectUiView(ui, selectedUiViews.index(ui)>0)
