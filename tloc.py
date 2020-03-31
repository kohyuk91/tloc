# BSD 3-Clause License
#
# Copyright (c) 2020, Hyuk Ko
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

#
# Shout out to Frank Illing for the "World Space to Image Space" expression.
#

# Documentation
"""
"T"riangulate + "Loc"ator

Manual point triangulation is great for accurate set reconstruction.
However doing more than 100 point triangulations by hand is a not-so-fun task.
TLOC helps you to triangulate points with ease in Maya.

https://github.com/kohyuk91/tloc
"""

# Basic Workflow
"""
1. Hover the cursor above the viewport and execute the script with a HOTKEY(e.g. Alt + Shift + X)!
2. You have created a "Reference Frame"
3. "Center3D camera" is created and centered to TLOC.
4. Move to another keyframe(or camera), and adjust TLOC's depth attribute until it matches with the "Reference Frame".
5. Press the same HOTKEY to remove the "Center3D camera".
"""

# Usage
# Execute the code below via Hotkey.
# e.g) Alt + Shift + X
"""
import tloc
reload(tloc)
tloc.main()
"""

# Versions
# 0.0.4 - Script will run differently based on selection.
# 0.0.3 - TLOC scale continuity.
# 0.0.2 - No need to select depth attribute in channelbox.
# 0.0.1 - Initial Release


import maya.cmds as mc
import maya.OpenMaya as om
import maya.OpenMayaUI as omui
try:
    from Qt import QtGui, QtWidgets, QtCore # Requires Qt.py for Maya 2016 and under.
except:
    from PySide2 import QtGui, QtWidgets, QtCore

import random


def center3d(active3dViewCamShape, active3dViewCamTrans, tlocTrans, zoom=0.2):
    """
    Centers the viewport to TLOC.

    < Note >
    This may not work properly if the Image Plane's Aspect Ratio and Device Aspect Ratio(in Render Setting) does not match.
    Image Plane Size: 1920 X 1080 (1.778)  and  Image Size: 1920 X 1080 (1.778) --> O
    Image Plane Size: 1920 X 1080 (1.778)  and  Image Size: 960 X 540 (1.778) --> O
    Image Plane Size: 1920 X 1080 (1.778) and  Image Size: 3000 X 1500 (1.5) --> X
    """
    # Set Imageplane to show in "All Views"
    try:
        active3dViewCamImgPlaneShape = mc.listRelatives(active3dViewCamShape, allDescendents=True, type='imagePlane')[0]
        mc.imagePlane(active3dViewCamImgPlaneShape, e=True, showInAllViews=True)
    except:
        active3dViewCamImgPlaneShape = None

    # Create Centroid
    centroidLoc = mc.spaceLocator(name='centroid_#')[0]
    mc.setAttr(centroidLoc+'.v', 0)
    mc.pointConstraint(tlocTrans, centroidLoc, maintainOffset=False)

    # Create Center3D Camera
    center3dCam = mc.camera(name=active3dViewCamTrans + '_Center3D_' + centroidLoc)[0]
    center3dCamTrans = mc.ls(mc.parent(center3dCam, active3dViewCamTrans, relative=True), long=True)[0]
    center3dCamShape = mc.listRelatives(center3dCamTrans, shapes=True, fullPath=True)[0]

    # LookThru Center3D Camera
    panelWithFocus = mc.getPanel(withFocus=True)
    mc.lookThru(panelWithFocus, center3dCamShape)

    # Set Zoom
    mc.setAttr(center3dCamShape+".panZoomEnabled", 1)
    mc.setAttr(center3dCamShape+".zoom", zoom)

    # Sync Shape Attributes. Active 3D View Cam & Center 3D Cam
    mc.connectAttr(active3dViewCamShape+'.hfa' , center3dCamShape+'.hfa')
    mc.connectAttr(active3dViewCamShape+'.vfa' , center3dCamShape+'.vfa')
    mc.connectAttr(active3dViewCamShape+'.fl' , center3dCamShape+'.fl')
    mc.connectAttr(active3dViewCamShape+'.nearClipPlane' , center3dCamShape+'.nearClipPlane')
    mc.connectAttr(active3dViewCamShape+'.farClipPlane' , center3dCamShape+'.farClipPlane')

    # Center3D Expression
    exp =  'global proc float[] cTtransformPoint(float $mtx[], float $pt[]) // multiply 4x4 matrix with 4x vector\n'
    exp += '{\n'
    exp += '    float $res[] = {};\n'
    exp += '    if(`size $pt` == 3)\n'
    exp += '    $pt[3] = 1.0;\n'
    exp += '    for($i=0;$i<4;$i++){\n'
    exp += '    float $tmp = 0;\n'
    exp += '    for($k=0;$k<4;$k++){\n'
    exp += '        $tmp += $pt[$k] * $mtx[$k * 4 + $i];\n'
    exp += '    };\n'
    exp += '    $res[$i] = $tmp;\n'
    exp += '    };\n'
    exp += '    return $res;\n'
    exp += '};\n'

    exp += 'global proc float[] cGetProjectionMatrix(string $shape) //get camera projection matrix\n'
    exp += '{\n'
    exp += '    float $res[] = {};\n'
    exp += '    if(`objExists $shape` && `nodeType $shape` == "camera"){\n'
    exp += '    python "import maya.OpenMaya as om";\n'
    exp += '    python "list = om.MSelectionList()";\n'
    exp += '    python (' + '"' + 'list.add(' + "'"+ '"' + '+ $shape + ' + '"' + "')" + '");\n'
    exp += '    python "depNode = om.MObject()";\n'
    exp += '    python "list.getDependNode(0, depNode)";\n'
    exp += '    python "camFn = om.MFnCamera(depNode)";\n'
    exp += '    python "pMtx = om.MFloatMatrix()";\n'
    exp += '    python "pMtx = camFn.projectionMatrix()";\n'
    exp += '    for($i=0;$i<=3;$i++){\n'
    exp += '        for($k=0;$k<=3;$k++)\n'
    exp += '        $res[`size $res`] = `python ("pMtx(" + $i + ", " + $k + ")")`;\n'
    exp += '    };\n'
    exp += '    };\n'
    exp += '    return $res;\n'
    exp += '};\n'

    exp += 'global proc float[] cWorldSpaceToImageSpace(string $camera, float $worldPt[])\n'
    exp += '{\n'
    exp += '    string $camShape[] = `ls -dag -type "camera" $camera`;\n'
    exp += '    if(! `size $camShape`)\n'
    exp += '    return {};\n'
    exp += '    string $cam[] = `listRelatives -p -f $camShape`;\n'
    exp += '    float $cam_inverseMatrix[] = `getAttr ($cam[0] + ".worldInverseMatrix")`;\n'
    exp += '    float $cam_projectionMatrix[] = `cGetProjectionMatrix $camShape[0]`;\n'
    exp += '    float $ptInCamSpace[] = `cTtransformPoint $cam_inverseMatrix $worldPt`;\n'
    exp += '    float $projectedPoint[] = `cTtransformPoint $cam_projectionMatrix $ptInCamSpace`;\n'
    exp += '    float $resultX = (($projectedPoint[0] / $projectedPoint[3]));\n'
    exp += '    float $resultY = (($projectedPoint[1] / $projectedPoint[3]));\n'
    exp += '    return {$resultX, $resultY};\n'
    exp += '};\n'

    exp += 'float $xy[] = cWorldSpaceToImageSpace("' + active3dViewCamTrans +'", {'+ centroidLoc +'.translateX,'+centroidLoc+'.translateY,'+centroidLoc+'.translateZ});\n'
    exp += center3dCamShape + '.horizontalFilmOffset = ($xy[0] *' + active3dViewCamShape + '.hfa)/2 ;\n'
    exp += center3dCamShape + '.verticalFilmOffset = ($xy[1] *'+ active3dViewCamShape + '.vfa)/2 ;\n'

    mc.expression(s=exp, object=center3dCamShape)


def dragAttrContext(tlocTrans):
    dragAttrContextName = "dragAttrContext"
    if not mc.dragAttrContext(dragAttrContextName, ex=True):
        mc.dragAttrContext(dragAttrContextName)
    mc.dragAttrContext(dragAttrContextName, e=True, ct=tlocTrans+".depth")
    mc.setToolTo(dragAttrContextName)


def getActive3dViewCam():
    active3dView = omui.M3dView.active3dView()
    active3dViewCamDagPath = om.MDagPath()
    active3dView.getCamera(active3dViewCamDagPath)
    active3dViewCamShape = active3dViewCamDagPath.fullPathName()
    active3dViewCamTrans = mc.listRelatives(active3dViewCamShape, parent=True, fullPath=True)[0]

    return active3dViewCamShape, active3dViewCamTrans


def pointTriangulationMode(active3dViewCamShape, active3dViewCamTrans, tlocTrans):
    # Center3D on TLOC
    center3d(active3dViewCamShape, active3dViewCamTrans, tlocTrans)
    # Select TLOC
    mc.select(tlocTrans)
    mc.evalDeferred("import maya.cmds as mc;mc.outlinerEditor('outlinerPanel1', edit=True, showSelected=True)")
    # Set Tool to "Drag Attr Context"
    dragAttrContext(tlocTrans)


def getClipboardText():
    clipboard = QtWidgets.QApplication.clipboard()
    text = clipboard.text()
    return text


def setClipboardText(text):
    clipboard = QtWidgets.QApplication.clipboard()
    clipboard.setText(text)


def createTloc(active3dViewCamShape, active3dViewCamTrans, depth=10, parent=""):
    """
    Creates "TLOC" and "Center3D camera".
    You can do point triangulation and quality check at the same time.

    < Note >
    - You might not see TLOC if the image plane is to close to the camera. Give the image plane's "Depth" a higher value to fix this problem.
    """
    currentTime = int(mc.currentTime(q=True))
    indexList = [6,9,13,14,16,17,18]
    random_index = random.choice(indexList)


    # Create TLOC & TLOC GRP
    tlocTrans = mc.spaceLocator(name="tloc_{}f_#".format(currentTime))[0]
    tlocShape = mc.listRelatives(tlocTrans, shapes=True)[0]
    tlocGrp = mc.group(tlocTrans, name="{}_grp".format(tlocTrans))

    # Add Depth Attribute to TLOC
    mc.addAttr(tlocTrans, shortName="depth", longName="Depth", attributeType="float", defaultValue=depth)
    mc.setAttr(tlocTrans+".depth", keyable=True)

    # Connect Depth Attribute to ScaleXYZ
    mc.connectAttr(tlocTrans+".depth", tlocTrans+".sx")
    mc.connectAttr(tlocTrans+".depth", tlocTrans+".sy")
    mc.connectAttr(tlocTrans+".depth", tlocTrans+".sz")

    # Set TLOC Color
    mc.setAttr(tlocShape+".overrideEnabled", 1)
    mc.setAttr(tlocShape+".overrideColor", random_index)


    # Get Active 3D View Camera
    active3dViewCamShape, active3dViewCamTrans = getActive3dViewCam()


    # Store Near Clip Plane value
    nearClipPlaneStored = mc.getAttr(active3dViewCamShape+".nearClipPlane")

    # Temporarily set Near Clip Plane
    mc.setAttr(active3dViewCamShape+".nearClipPlane", depth)
    mc.refresh(force=True) # Need to refresh the viewport to apply the new near clip plane value.

    # Get world space scale of Active 3D View Camera
    active3dViewCamWorldSpaceScale = mc.xform(active3dViewCamTrans, q=True, worldSpace=True, scale=True)[0] # Just return sx


    # Get Cursor Position
    cursorPos = QtGui.QCursor.pos()
    widget = QtWidgets.QApplication.widgetAt(cursorPos)
    widgetHeight = widget.height()
    relpos = widget.mapFromGlobal(cursorPos)

    position = om.MPoint()  # 3D point with double-precision coordinates
    direction = om.MVector()  # 3D vector with double-precision coordinates

    omui.M3dView().active3dView().viewToWorld(
        relpos.x(),
        widgetHeight - relpos.y(), # The relpos.y() alone returns a mirrored position. Must subtract it with widgetHeight.
        position,  # world point
        direction)


    # Orient TLOC GRP to Camera
    oc = mc.orientConstraint(active3dViewCamTrans, tlocGrp, maintainOffset=False)
    mc.delete(oc)

    # Move TLOC GRP to Cursor Position
    mc.xform(tlocGrp, worldSpace=True, translation=[position.x, position.y, position.z])

    # Move TLOC GRP pivot to Camera Position
    active3dViewCamPos = mc.xform(active3dViewCamTrans, q=True, worldSpace=True, translation=True)
    mc.xform(tlocGrp, worldSpace=True, pivots=[active3dViewCamPos[0], active3dViewCamPos[1], active3dViewCamPos[2]])

    # Move TLOC GRP under parent
    if parent != "":
        mc.parent(tlocGrp, parent)

    setClipboardText(parent)

    """
    Eventually TLOC GRP has to go inside camera or object point group.
    Locking translation and rotation attributes can make things complicated.

    # Lock TLOC GRP translation & rotation attributes
    axisList = ["x", "y", "z"]
    attrList = ["t", "r"]
    for axis in axisList:
        for attr in attrList:
            mc.setAttr("{0}.{1}{2}".format(tlocGrp, attr, axis), lock=True)
    """


    # Set TLOC Depth & Scale
    mc.expression(s="""
                    {0}.sx = {1}.sx;
                    {0}.sy = {1}.sy;
                    {0}.sz = {1}.sz;
                    """.format(tlocGrp, tlocTrans), object=tlocGrp)
    mc.expression(s="""
                    {0}.lsx = 1 / {1}.sx / {2} * {3};
                    {0}.lsy = 1 / {1}.sy / {2} * {3};
                    {0}.lsz = 0;
                    """.format(tlocShape, tlocGrp, depth, active3dViewCamWorldSpaceScale), object=tlocGrp)

    # Just for marking the Creation Frame
    mc.setKeyframe(tlocTrans+".rx", value=0, time=[currentTime])


    # Set to point triangulation mode
    pointTriangulationMode(active3dViewCamShape, active3dViewCamTrans, tlocTrans)

    # Set Near Clip Plane back to stored value
    mc.setAttr(active3dViewCamShape+".nearClipPlane", nearClipPlaneStored)


def main():
    if mc.objExists("*centroid*"):
        mc.delete("*centroid*") # Delete Centroid and Center3D nodes

        lastParent = getClipboardText()
        if lastParent != "":
            mc.select(lastParent, replace=True)
            return

        mc.select(clear=True)
        return

    # Get Active 3D View Camera
    active3dViewCamShape, active3dViewCamTrans = getActive3dViewCam()

    # Get selection
    sel = mc.ls(selection=True, long=True)

    if len(sel) == 0: # If nothing is selected and you press the TLOC hotkey, a new TLOC will be created.
        createTloc(active3dViewCamShape, active3dViewCamTrans)
        return
    elif len(sel) == 1: # If a single item is selected...
        try:
            selShape = mc.listRelatives(sel[0], fullPath=True, shapes=True)[0] # Get selected object's shape node.
            object_type = mc.objectType(selShape) # Get object type.
        except:
            object_type = "transform" # If there is no shape node pass "transform".

        if object_type == "locator" and "tloc" in sel[0]: # and it is TLOC. Jump to point triangulation mode(Center3D & Drag Attr Context).
            pointTriangulationMode(active3dViewCamShape, active3dViewCamTrans, sel[0])
            return
        elif object_type == "imagePlane": # and it is image plane. A new TLOC will be created.
            createTloc(active3dViewCamShape, active3dViewCamTrans)
            return
        else: # and it is something other than TLOC. A new TLOC will be created and parented to the selected item.
            createTloc(active3dViewCamShape, active3dViewCamTrans, parent=sel[0])
            return
    elif len(sel) > 1:
        mc.warning("Too many objects selected. Select 0 or 1 item.")
        return
