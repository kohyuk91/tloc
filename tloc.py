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
"""

# Basic Workflow
"""
1. Hover the cursor above the viewport and execute the script with a HOTKEY(e.g. Alt + Shift + X)!
2. You have created a "Reference Frame"
3. "Center3D camera" is created and centered to the locator.
4. Move to another keyframe(or camera), and adjust the "Depth" attribute in TLOC until it matches with the "Reference Frame".
5. Press HOTKEY to remove the "Center3D camera".
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
# 0.0.1 - Initial Release


import maya.cmds as mc
import maya.OpenMaya as om
import maya.OpenMayaUI as omui
try:
    from Qt import QtGui, QtWidgets, QtCore # Requires Qt.py for Maya 2016 and under.
except:
    from PySide2 import QtGui, QtWidgets, QtCore

import random


def getMDagPath(name):
    sel_list = om.MSelectionList()
    sel_list.add(name)
    dag = om.MDagPath()
    component = om.MObject()
    sel_list.getDagPath(0, dag, component)
    return dag


def center3d(active3dViewCamShape, active3dViewCamTrans, active3dViewCamZoom, tlocTrans):
    """
    Centers the viewport to TLOC.

    * Some Notes *
    * This may not work properly if the Image Plane's Aspect Ratio and Device Aspect Ratio(in Render Setting) does not match.
    * Image Plane Size: 1920 X 1080 (1.778)  and  Image Size: 1920 X 1080 (1.778) --> O
    * Image Plane Size: 1920 X 1080 (1.778)  and  Image Size: 960 X 540 (1.778) --> O
    * Image Plane Size: 1920 X 1080 (1.778) and  Image Size: 3000 X 1500 (1.5) --> X
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
    mc.setAttr(center3dCamShape+".zoom", active3dViewCamZoom)

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

def main(depth=100.0, do_center3d=True, zoom_history=False):
    """
    Creates TLOC and Center3D camera to do point triangulation and quality check at the same time.

    * Some Notes *
    You might not see the locator in the following cases...
    1. Image Plane is to close to the camera. --> Give the "Depth" attribute a higher value.
    2. Near & Far clipping plane too low.
    """

    # Delete Center3D nodes
    if mc.objExists("*centroid*") == True:
        mc.delete('centroid_*','*_Center3D_*')
        return

    currentTime = int(mc.currentTime(q=True))
    indexList = [6,9,13,14,16,17,18]
    random_index = random.choice(indexList)

    # Create TLOC
    tlocTrans = mc.spaceLocator(name="tloc_{}f_#".format(currentTime))[0]
    tlocShape = mc.listRelatives(tlocTrans, shapes=True)[0]
    tlocGrp = mc.group(tlocTrans, name="{}_grp_#".format(tlocTrans))

    # Add Depth Attribute to TLOC
    mc.addAttr(tlocTrans, shortName="depth", longName="Depth", attributeType="float", defaultValue=1)
    mc.setAttr(tlocTrans+".depth", keyable=True)

    # Connect Depth Attribute to ScaleXYZ
    mc.connectAttr(tlocTrans+".depth", tlocTrans+".sx")
    mc.connectAttr(tlocTrans+".depth", tlocTrans+".sy")
    mc.connectAttr(tlocTrans+".depth", tlocTrans+".sz")

    # Set TLOC Color
    mc.setAttr(tlocShape+".overrideEnabled", 1)
    mc.setAttr(tlocShape+".overrideColor", random_index)


    # Get Active 3D View Camera
    active3dView = omui.M3dView.active3dView()
    active3dViewCamDagPath = om.MDagPath()
    active3dView.getCamera(active3dViewCamDagPath)
    active3dViewCamShape = active3dViewCamDagPath.fullPathName()
    active3dViewCamTrans = mc.listRelatives(active3dViewCamShape, parent=True, fullPath=True)[0]

    # Get Cursor Position
    cursorPos = QtGui.QCursor.pos()
    widget = QtWidgets.QApplication.widgetAt(cursorPos)
    widgetHeight = widget.height()
    relpos = widget.mapFromGlobal(cursorPos)

    position = om.MPoint()  # 3D point with double-precision coordinates
    direction = om.MVector()  # 3D vector with double-precision coordinates

    omui.M3dView().active3dView().viewToWorld(
        relpos.x(),
        widgetHeight - relpos.y(),
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

    # Set TLOC Depth & Scale
    mc.expression(s="""
                    {0}.sx = {1}.sx * {2};
                    {0}.sy = {1}.sy * {2};
                    {0}.sz = {1}.sz * {2};
                    """.format(tlocGrp, tlocTrans, depth), object=tlocGrp)
    mc.expression(s="""
                    {0}.lsx = 1/{1}.sx;
                    {0}.lsy = 1/{1}.sy;
                    {0}.lsz = 0;
                    """.format(tlocShape, tlocGrp), object=tlocGrp)

    # Just for marking the Creation Frame
    mc.setKeyframe(tlocTrans+".rx", value=0, time=[currentTime])


    # Center3D
    if do_center3d == False:
        pass
    else:
        if mc.getAttr(active3dViewCamShape+".panZoomEnabled") == 1 or zoom_history == True:
            active3dViewCamZoom = mc.getAttr(active3dViewCamShape+".zoom")
        else:
            active3dViewCamZoom = 0.20 # You have to zoom in for precision anyway...
        center3d(active3dViewCamShape, active3dViewCamTrans, active3dViewCamZoom, tlocTrans)


    # Select TLOC
    mc.select(tlocTrans)
    mc.evalDeferred("import maya.cmds as mc")
    mc.evalDeferred("mc.outlinerEditor('outlinerPanel1', edit=True, showSelected=True)")
