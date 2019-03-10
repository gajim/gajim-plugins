import logging

from gi.repository import Gtk as gtk
from gi.repository import Pango

from pygments.formatter import Formatter
from gajim.plugins.helpers import log
log = logging.getLogger('gajim.p.syntax_highlight')

class GTKFormatter(Formatter):
    name = 'GTK Formatter'
    aliases = ['textbuffer', 'gtk']
    filenames = []

    def __init__(self, **options):
        super(GTKFormatter, self).__init__(**options)
        #Formatter.__init__(self, **options)
        self.tags = {}
        self.mark = options.get('start_mark', None)

    @staticmethod
    def create_tag_for_token(ttype, highlighting_style):
        style = highlighting_style.style_for_token(ttype)
        tag = gtk.TextTag.new()
        if 'bgcolor' in style and not style['bgcolor'] is None:
            tag.set_property('background', '#%s' % style['bgcolor'])
        if 'bold' in style and style['bold']:
            tag.set_property('weight', Pango.Weight.BOLD)
        if 'border' in style and not style['border'] is None:
            pass
        if 'color' in style and not style['color'] is None:
            tag.set_property('foreground', '#%s' % style['color'])
        if 'italic' in style and style['italic']:
            tag.set_property('style', Pango.Style.ITALIC)
        if 'mono' in style and not style['mono'] is None:
            tag.set_property('family', 'Monospace')
            tag.set_property('family-set', True)
        if 'roman' in style and not style['roman'] is None:
            pass
        if 'sans' in style and not style['sans'] is None:
            tag.set_property('family', 'Sans')
            tag.set_property('family-set', True)
        if 'underline' in style and style['underline']:
            tag.set_property('underline', 'single')
        return tag


    def get_tag(self, ttype, buf):
        """
        Creates, stores and returs a tag for a given token type.

        This method ensures that a tag style is created only once.
        Furthermore, the tag will be added to the given Gtk.TextBuffer's tag table.
        """
        tag = None
        if ttype in self.tags:
            tag = self.tags[ttype]
        else:
            tag = GTKFormatter.create_tag_for_token(ttype, self.style)
            self.tags[ttype] = tag
            buf.get_tag_table().add(tag)
        return tag

    def set_insert_pos_mark(self, mark):
        self.mark = mark

    def format(self, tokensource, outfile):
        if not isinstance(outfile, gtk.TextBuffer) or outfile is None:
            log.warn("Did not get a buffer to format...")
            return
        buf = outfile

        end_iter    = buf.get_end_iter()

        start_mark  = self.mark
        start_iter  = buf.get_iter_at_mark(start_mark) if not start_mark is None \
                else end_iter

        last_ttype  = None
        last_start  = start_iter
        last_end    = buf.get_end_iter()
        last_fixed_start = last_start

        reset       = True

        for ttype, value in tokensource:
            search = None
            if last_ttype is not None and ttype != last_ttype:
                tag = self.get_tag(last_ttype, buf)

                buf.apply_tag(tag, last_fixed_start, last_end)

                search = last_end.forward_search(value, gtk.TextSearchFlags.TEXT_ONLY, end_iter)
                reset = True
            else:
                # in case last_ttype is None, i.e. first loop walkthrough:
                # last_start to end_iter is the full code block.
                search = last_start.forward_search(value, gtk.TextSearchFlags.TEXT_ONLY, end_iter)

            # Prepare for next iteration
            last_ttype = ttype
            if search is not None:
                (last_start, last_end) = search

                # If we've found the end of a sequence of similar type tokens or if
                # we are in the first loop iteration, set the fixed point
                if reset:
                    last_fixed_start = last_start
                    reset = False
            else:
                # Hm... Nothing found, but tags left? Seams there's nothing we
                # can do now.
                break
