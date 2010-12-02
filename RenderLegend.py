#!/usr/bin/python
#__license__ = "GPL"
__author__ = "Yves Cainaud"
from RenderLegendElement import renderLegendElement
import xml.dom.minidom as m
from xml.dom.minidom import getDOMImplementation

for zoom in range(1,19):
    doc = m.parse('legend_compact.xml')
    elements = doc.getElementsByTagName("element")
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
        renderLegendElement("osm_full.xml", type, listTag, zoom, 50,\
         'pics/'+str(zoom)+'-'+str(id)+'.png')

