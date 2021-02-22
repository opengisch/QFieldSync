# -*- coding: utf-8 -*-
"""
/***************************************************************************
 QFieldSync
                             -------------------
        begin                : 2020-07-13
        git sha              : $Format:%H$
        copyright            : (C) 2020 by OPENGIS.ch
        email                : info@opengis.ch
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""


import re


def to_cloud_title(title):
    return re.sub('[^A-Za-z0-9-_]','_', title)


def closure(cb):
    def wrapper(*closure_args, **closure_kwargs):
        def call(*args, **kwargs):
            return cb(*closure_args, *args, **closure_kwargs, **kwargs)

        return call

    return wrapper