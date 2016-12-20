import gtk
import pango

from pygments.formatter import Formatter

class GTKFormatter(Formatter):
    name = 'GTK Formatter'
    aliases = ['textbuffer', 'gtk']
    filenames = []

    def __init__(self, **options):
        super(GTKFormatter, self).__init__(**options)
        #Formatter.__init__(self, **options)
        self.tags = {}
        self.last_mark = None
        self.mark = options.get('start_mark', None)

    def insert(self, tb, pos, text):
        tb.insert(pos, text)
        return tb.get_end_iter()

    def get_tag(self, ttype, tb):
        tag = None
        if ttype in self.tags:
            tag = self.tags[ttype]
        else:
            style = self.style.style_for_token(ttype)
            tag = gtk.TextTag()
            if 'bgcolor' in style and not style['bgcolor'] is None:
                tag.set_property('background', '#%s' % style['bgcolor'])
            if 'bold' in style and style['bold']:
                tag.set_property('weight', pango.WEIGHT_BOLD)
            if 'border' in style and not style['border'] is None:
                #TODO
                pass
            if 'color' in style and not style['color'] is None:
                tag.set_property('foreground', '#%s' % style['color'])
            if 'italic' in style and style['italic']:
                tag.set_property('style', pango.STYLE_ITALIC)
            if 'mono' in style and not style['mono'] is None:
                tag.set_property('family', 'Monospace')
                tag.set_property('family-set', True)
            if 'roman' in style and not style['roman'] is None:
                #TODO
                pass
            if 'sans' in style and not style['sans'] is None:
                tag.set_property('family', 'Sans')
                tag.set_property('family-set', True)
            if 'underline' in style and style['underline']:
                tag.set_property('underline', 'single')
            self.tags[ttype] = tag
            tb.get_tag_table().add(tag)
        return tag

    def set_insert_pos_mark(self, mark):
        self.mark = mark

    def format(self, tokensource, tb=gtk.TextBuffer()):
        if not isinstance(tb, gtk.TextBuffer):
            raise TypeError("This Formatter expects a gtk.TextBuffer object as"\
                "'output' file argument.")
        ltype = None
        insert_at_iter = tb.get_iter_at_mark(self.mark) if not self.mark is None \
                else tb.get_end_iter()
        lstart_iter     = tb.create_mark(None, insert_at_iter, True)
        lend_iter       = tb.create_mark(None, insert_at_iter, False)
        for ttype, value in tokensource:
            if ttype == ltype:
                eiter = self.insert(tb, tb.get_iter_at_mark(lend_iter), value)
                #tb.move_mark(lend_iter, eiter)
            else:
                # set last buffer section properties
                if not ltype is None:
                    # set properties
                    tag = self.get_tag(ltype, tb)
                    if not tag is None:
                        tb.apply_tag(
                                tag,
                                tb.get_iter_at_mark(lstart_iter),
                                tb.get_iter_at_mark(lend_iter))
                tb.move_mark(lstart_iter, tb.get_iter_at_mark(lend_iter))
                eiter = self.insert(tb, tb.get_iter_at_mark(lend_iter), value)
                #tb.move_mark(lend_iter, eiter)
                ltype = ttype
        self.last_mark = lend_iter

    def get_last_mark(self):
        return self.last_mark
