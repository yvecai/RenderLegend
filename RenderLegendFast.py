#!/usr/bin/python
"""

"""
import mapnik
from mapnik import Osm, Map, load_map, save_map # allow us to change the mapFile datasource
from RenderLegendElement import createOsmElement, create_legend_stylesheet

import re
import StringIO
import tempfile
import os
import xml.dom.minidom as minidom
from xml.dom.minidom import getDOMImplementation
from lxml import etree
import Image
import ImageChops
import ImageFile

# lat-lon geometry elements
# faclat is the 'width' factor defining a common width for elements
# faclon is the 'height' factor
# rectangles have ratio faclat/faclon
faclat=0.003
faclon=0.006
sourceFile="osm.xml"
legendFile='legend_compact.xml'
imageWidth=50

dir='pics/'
d = os.path.dirname(dir)
if not os.path.exists(d):
    os.makedirs(d)

"""
# 'Fake' load a map to use mapnik libxml2 support for large xml files
mSource = mapnik.Map(1,1)
mapnik.load_map(mSource,sourceFile)
inputstylesheet=mapnik.save_map_to_string(mSource)
"""
# serialize map file with external entities
inputstylesheet=etree.tostring(etree.parse(sourceFile))

# the mapfile (stylesheet made jsut for legned element rendering
# is returned as a string, no file is written on disk
# then we'll use mapnik.load_map_from_string
mapfile = create_legend_stylesheet(inputstylesheet)

doc = minidom.parse(legendFile)
elements = doc.getElementsByTagName("element")

for zoom in range(1,19):
    for e in elements:
        id=str(e.getElementsByTagName("id")[0].\
        firstChild.nodeValue).strip('\n ')
        try: caption=e.getAttribute("caption").strip('\n ')
        except: caption=''
        type=str(e.getElementsByTagName("type")[0].firstChild.\
        nodeValue).strip('\n ')
        tags=e.getElementsByTagName("tag")
        listTag=[]
        for t in tags:
            key=t.getAttribute("k")
            value=t.getAttribute("v")
            listTag.append(str('['+key+']=\''+value+'\''))
        map_uri=dir+str(zoom)+'-'+str(id)+'.png' #'-'+caption+
        #we create a new element, which return its bbox
        osmStr, bound = createOsmElement(type, listTag, zoom)
        # create a named temporary file
        # l.datasource = Osm(file=osmFile.name) need a file name
        # we cannot pass a StringIO nor a string, nor a unnammed
        # temporary file
        osmFile = tempfile.NamedTemporaryFile(mode='w+t')
        osmFile.write(osmStr) #write the osm file
        osmFile.seek(0) #rewind
        #---------------------------------------------------
        
        # Set up projections
        # long/lat in degrees, aka ESPG:4326 and "WGS 84" 
        lonlat = mapnik.Projection('+proj=longlat +datum=WGS84')
    
        #bbbox =(lon,lat,maxlon,maxlat)
        ratio= abs((bound[2]-bound[0])/(bound[3]-bound[1]))
        width = imageWidth
        height = int(width/ratio*1)+1 #+1 for highway=path does not look blurry
        m = mapnik.Map(width,height)
        
        mapnik.load_map_from_string(m,mapfile)
        m.srs = lonlat.params()
        for l in m.layers:
            l.datasource = Osm(file=osmFile.name)
            l.srs = lonlat.params()
        
        bbox =lonlat.forward(mapnik.Envelope(mapnik.Coord(bound[0],bound[1]),\
         mapnik.Coord(bound[2],bound[3])))
        m.zoom_to_box(bbox)
        
        im = mapnik.Image(width,height)
        
        mapnik.render(m, im)
        #print osmFile.read()
        osmFile.close() # closing the datasource

        view = im.view(0,0,width,height) # x,y,width,height
        #print "saving ", map_uri
        #view.save(map_uri,'png')
        
        #'save' the image in a string
        imgStr=view.tostring('png')
        
        # reopen the saved image with PIL to count the color
        # if 1, the pic is empty 
        #img = Image.open(map_uri)
        
        # kind of StringIO() for images instead:
        imgParser=ImageFile.Parser()
        imgParser.feed(imgStr)
        img = imgParser.close()
        
        if len(img.getcolors()) == 1:
            print "empty file not saved", map_uri
            #delete the pic file if empty
            #os.remove(map_uri)
        else:
            # Crop the file to its smaller extent
            # Cropping the pic allow a much concise html page formatting,
            # use CSS for the rest
            img256=img.convert('L')
            imgbg=ImageChops.constant(img256,img256.getpixel((0,0)))
            box=ImageChops.difference(img256, imgbg).getbbox()
            out=img.crop(box)
            print "saving ", map_uri
            out.save(map_uri)
            

