#!/usr/bin/python
#__license__ = "GPL"
__author__ = "Yves Cainaud"
from RenderLegendElement import renderLegendElement
import xml.dom.minidom
from xml.dom.minidom import getDOMImplementation
import os

sourceFile="osm.xml"
legendFile='legend_compact.xml'
imageWidth=50
dir='pics/'

d = os.path.dirname(dir)
if not os.path.exists(d):
    os.makedirs(d)

doc = xml.dom.minidom.parse(legendFile)
elements = doc.getElementsByTagName("element")

for zoom in range(18,19):

    for e in elements:
        id=str(e.getElementsByTagName("id")[0].\
        firstChild.nodeValue).strip('\n ')
        type=str(e.getElementsByTagName("type")[0].firstChild.\
        nodeValue).strip('\n ')
        tags=e.getElementsByTagName("tag")
        listTag=[]
        for t in tags:
            key=t.getAttribute("k")
            value=t.getAttribute("v")
            listTag.append(str('['+key+']=\''+value+'\''))
        renderLegendElement(sourceFile, type, listTag, zoom, 50,\
         dir+str(zoom)+'-'+str(id)+'.png')

