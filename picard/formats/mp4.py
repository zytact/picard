# -*- coding: utf-8 -*-
#
# Picard, the next-generation MusicBrainz tagger
# Copyright (C) 2006 Lukáš Lalinský
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

from mutagen.mp4 import MP4, MP4Cover
from picard.file import File
from picard.metadata import Metadata
from picard.util import encode_filename

class MP4File(File):
    EXTENSIONS = [".m4a", ".m4b", ".m4p", ".mp4"]
    NAME = "MPEG-4 Audio"

    __text_tags = {
        "\xa9ART": "artist",
        "\xa9nam": "title",
        "\xa9alb": "album",
        "\xa9wrt": "composer",
        "aART": "albumartist",
        "\xa9grp": "grouping",
        "\xa9day": "date",
        "\xa9gen": "genre",
        "\xa9lyr": "lyrics",
        "\xa9too": "encodedby",
        "cprt": "copyright",
        "soal": "albumsort",
        "soaa": "albumartistsort",
        "soar": "artistsort",
        "sonm": "titlesort",
        "soco": "composersort",
        "sosn": "showsort",
        "tvsh": "show",
        "purl": "podcasturl",
    }
    __r_text_tags = dict([(v, k) for k, v in __text_tags.iteritems()])

    __bool_tags = {
        "pcst": "podcast",
        "cpil": "compilation",
        "pgap": "gapless",
    }
    __r_bool_tags = dict([(v, k) for k, v in __bool_tags.iteritems()])

    __freeform_tags = {
        "----:com.apple.iTunes:MusicBrainz Track Id": "musicbrainz_trackid",
        "----:com.apple.iTunes:MusicBrainz Artist Id": "musicbrainz_artistid",
        "----:com.apple.iTunes:MusicBrainz Album Id": "musicbrainz_albumid",
        "----:com.apple.iTunes:MusicBrainz Album Artist Id": "musicbrainz_albumartistid",
        "----:com.apple.iTunes:MusicIP PUID": "musicip_puid",
        "----:com.apple.iTunes:MusicBrainz Album Status": "releasestatus",
        "----:com.apple.iTunes:MusicBrainz Album Release Country": "releasecountry",
        "----:com.apple.iTunes:MusicBrainz Album Type": "releasetype",
        "----:com.apple.iTunes:MusicBrainz Disc Id": "musicbrainz_discid",
        "----:com.apple.iTunes:MusicBrainz TRM Id": "musicbrainz_trmid",
        "----:com.apple.iTunes:ASIN": "asin",
        "----:com.apple.iTunes:Barcode": "barcode",
        "----:com.apple.iTunes:Producer": "producer",
        "----:com.apple.iTunes:Lyricist": "lyricist",
        "----:com.apple.iTunes:Conductor": "conductor",
        "----:com.apple.iTunes:Engineer": "engineer",
        "----:com.apple.iTunes:Mixer": "mixer",
        "----:com.apple.iTunes:DJMixer": "djmixer",
        "----:com.apple.iTunes:ISRC": "isrc",
        "----:com.apple.iTunes:Media": "media",
        "----:com.apple.iTunes:Label": "label",
        "----:com.apple.iTunes:CatalogNumber": "catalognumber",
        "----:com.apple.iTunes:Subtitle": "subtitle",
        "----:com.apple.iTunes:DiscSubtitle": "discsubtitle",
        "----:com.apple.iTunes:Mood": "mood",
    }
    __r_freeform_tags = dict([(v, k) for k, v in __freeform_tags.iteritems()])

    def _load(self, filename):
        self.log.debug("Loading file %r", filename)
        file = MP4(encode_filename(filename))

        metadata = Metadata()
        for name, values in file.tags.items():
            if name in self.__text_tags:
                for value in values:
                    metadata.add(self.__text_tags[name], value)
            elif name in self.__bool_tags:
                metadata.add(self.__bool_tags[name], values and '1' or '0')
            elif name in self.__freeform_tags:
                for value in values:
                    value = value.strip("\x00").decode("utf-8", "replace")
                    metadata.add(self.__freeform_tags[name], value)
            elif name == "trkn":
                metadata["tracknumber"] = str(values[0][0])
                metadata["totaltracks"] = str(values[0][1])
            elif name == "disk":
                metadata["discnumber"] = str(values[0][0])
                metadata["totaldiscs"] = str(values[0][1])
            elif name == "covr":
                for value in values:
                    if value.format == value.FORMAT_JPEG:
                        metadata.add_image("image/jpeg", value)
                    else:
                        metadata.add_image("image/png", value)

        self._info(metadata, file)
        return metadata

    def _save(self, filename, metadata, settings):
        self.log.debug("Saving file %r", filename)
        file = MP4(encode_filename(self.filename))

        if settings["clear_existing_tags"]:
            file.tags.clear()

        for name, values in metadata.rawitems():
            if name in self.__r_text_tags:
                file.tags[self.__r_text_tags[name]] = values
            elif name in self.__r_bool_tags:
                file.tags[self.__r_bool_tags[name]] = (values[0] == '1')
            elif name in self.__r_freeform_tags:
                values = [v.encode("utf-8") for v in values]
                file.tags[self.__r_freeform_tags[name]] = values

        if "tracknumber" in metadata:
            if "totaltracks" in metadata:
                file.tags["trkn"] = [(int(metadata["tracknumber"]),
                                      int(metadata["totaltracks"]))]
            else:
                file.tags["trkn"] = [(int(metadata["tracknumber"]), 0)]

        if "discnumber" in metadata:
            if "totaldiscs" in metadata:
                file.tags["disk"] = [(int(metadata["discnumber"]),
                                      int(metadata["totaldiscs"]))]
            else:
                file.tags["disk"] = [(int(metadata["discnumber"]), 0)]

        covr = []
        for mime, data in metadata.images:
            if mime == "image/jpeg":
                covr.append(MP4Cover(data, format=MP4Cover.FORMAT_JPEG))
            else:
                covr.append(MP4Cover(data, format=MP4Cover.FORMAT_PNG))
        if covr:
            file.tags["covr"] = covr

        file.save()

    def supports_tag(self, name):
        return name in self.__r_text_tags or name in self.__r_bool_tags or name in self.__r_freeform_tags

