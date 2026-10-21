"""
Sskid Obfuscator v2 — Android (Kivy)
Build with buildozer or GitHub Actions
"""

import random
import base64
import re
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.core.clipboard import Clipboard
from kivy.utils import get_color_from_hex
from kivy.metrics import dp
from kivy.core.window import Window

# ═══════════════════════════════════════════════════
#  OBFUSCATION CORE
# ═══════════════════════════════════════════════════

class SskidV2:
    ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"

    def __init__(self, src, seed=None):
        self.src = src
        if seed is not None:
            random.seed(seed)
        self.sig = ''.join(random.choice(self.ALPHA) for _ in range(32))
        self.k1, self.k2, self.k3 = self._derive_keys(self.sig)
        self.strings = []
        self.suffix = ''.join(random.choice("0123456789abcdef") for _ in range(4))

    def _derive_keys(self, sig):
        h1 = []
        acc = 0
        for c in sig.encode():
            acc = (acc * 31 + c) & 0xFFFFFFFF
            h1.append(acc & 0xFF)
        while len(h1) < 16:
            acc = (acc * 31 + (len(h1) * 7)) & 0xFFFFFFFF
            h1.append(acc & 0xFF)

        h2 = []
        acc2 = 0x12345678
        for c in sig.encode():
            acc2 = (acc2 * 17 + c + 42) & 0xFFFFFFFF
            h2.append(acc2 & 0xFF)
        while len(h2) < 16:
            acc2 = (acc2 * 17 + len(h2)) & 0xFFFFFFFF
            h2.append(acc2 & 0xFF)

        k1 = bytes(h1[:16])
        k2 = bytes(h2[:16])
        k3 = bytes(a ^ b for a, b in zip(k1, k2))
        return k1, k2, k3

    def _encrypt(self, data):
        if isinstance(data, str):
            data = data.encode('utf-8', errors='replace')
        b = bytearray(data)
        for i in range(len(b)):
            b[i] ^= self.k1[i % 16]
        for i in range(len(b)):
            b[i] ^= self.k2[i % 16]
        for i in range(len(b)):
            b[i] ^= self.k3[i % 16]
            b[i] ^= (i + 1) & 0xFF
        return base64.b64encode(bytes(b)).decode()

    def _lua_unescape(self, s):
        out = bytearray()
        i = 0
        esc = {'n': 10, 't': 9, 'r': 13, 'a': 7, 'b': 8,
               'f': 12, 'v': 11, '\\': 92, '"': 34, "'": 39}
        while i < len(s):
            c = s[i]
            if c == '\\' and i + 1 < len(s):
                i += 1
                d = s[i]
                if d.isdigit():
                    num = d
                    while i + 1 < len(s) and len(num) < 3 and s[i + 1].isdigit():
                        i += 1
                        num += s[i]
                    out.append(int(num) & 0xFF)
                else:
                    out.append(esc.get(d, ord(d)))
            else:
                out.append(ord(c))
            i += 1
        return bytes(out)

    def _tokenize(self, s):
        i = 0
        n = len(s)
        while i < n:
            if s[i:i+2] == '--':
                m = re.match(r'--\[(=*)\[', s[i:])
                if m:
                    close = ']' + m.group(1) + ']'
                    j = s.find(close, i + m.end())
                    j = n if j < 0 else j + len(close)
                else:
                    j = s.find('\n', i)
                    j = n if j < 0 else j
                yield ('comment', i, j, s[i:j])
                i = j
                continue

            if s[i] == '[':
                m = re.match(r'\[(=*)\[', s[i:])
                if m:
                    close = ']' + m.group(1) + ']'
                    j = s.find(close, i + m.end())
                    j = n if j < 0 else j + len(close)
                    yield ('long_string', i, j, s[i:j])
                    i = j
                    continue

            if s[i] in '"\'':
                q = s[i]
                j = i + 1
                while j < n:
                    if s[j] == '\\':
                        j += 2
                        continue
                    if s[j] == q:
                        j += 1
                        break
                    j += 1
                yield ('string', i, j, s[i:j])
                i = j
                continue

            j = i
            while j < n and s[j] not in '"\'-[':
                j += 1
            yield ('code', i, j, s[i:j])
            i = j

    def _transform(self):
        parts = []
        for kind, _, _, content in self._tokenize(self.src):
            if kind == 'string':
                inner = content[1:-1]
                try:
                    decoded = self._lua_unescape(inner)
                except Exception:
                    parts.append(content)
                    continue
                self.strings.append(self._encrypt(decoded))
                parts.append(f'_S_{self.suffix}({len(self.strings)})')
            elif kind == 'long_string':
                m = re.match(r'\[(=*)\[(.*)\]\1\]', content, re.DOTALL)
                decoded = (m.group(2) if m else content[2:-2]).encode('utf-8')
                self.strings.append(self._encrypt(decoded))
                parts.append(f'_S_{self.suffix}({len(self.strings)})')
            else:
                parts.append(content)
        return ''.join(parts)

    def _hash(self, s):
        h = 0
        for b in s.encode('utf-8', errors='replace'):
            h = (h * 31 + b) % 2147483647
        return h

    def _prologue(self):
        sfx = self.suffix
        return f'''
local _SIG_{sfx} = "{self.sig}"
local _OK_{sfx} = false
local _FAILED_{sfx} = false

local function _bxor_{sfx}(a, b)
    local r, bit = 0, 1
    while a > 0 or b > 0 do
        local aa, bb = a % 2, b % 2
        if aa ~= bb then r = r + bit end
        a = math.floor(a / 2); b = math.floor(b / 2); bit = bit * 2
    end
    return r
end

local function _hash_{sfx}(s)
    local h = 0
    for i = 1, #s do h = (h * 31 + s:byte(i)) % 2147483647 end
    return h
end

local function _read_self_{sfx}()
    local ok, info = pcall(debug.getinfo, 1, "S")
    if not ok or not info or not info.source then return nil end
    local s = info.source
    if s:sub(1,1) ~= "@" then return nil end
    local path = s:sub(2)
    if not path or path == "" then return nil end
    if readfile then
        local ok2, c = pcall(readfile, path)
        if ok2 and c and #c > 0 then return c end
    end
    if io and io.open then
        local ok3, f = pcall(io.open, path, "r")
        if ok3 and f then
            local c = f:read("*a"); f:close()
            if c and #c > 0 then return c end
        end
    end
    return nil
end

local function _verify_{sfx}()
    local src = _read_self_{sfx}()
    if not src then
        _OK_{sfx} = true
        return true
    end
    src = src:gsub("\\r\\n", "\\n"):gsub("\\r", "\\n")
    local hdr_sig = src:match("SIG:%s*([%w]+)")
    if hdr_sig ~= _SIG_{sfx} then _FAILED_{sfx} = true; return false end
    local hdr_hash = src:match("HASH:%s*(%d+)")
    if not hdr_hash then _FAILED_{sfx} = true; return false end
    local region = src:match("%-%-<<SKV2_START>>\\n(.-)\\n%-%-<<SKV2_END>>")
    if not region then _FAILED_{sfx} = true; return false end
    if tostring(_hash_{sfx}(region)) ~= hdr_hash then _FAILED_{sfx} = true; return false end
    _OK_{sfx} = true
    return true
end

local function _derive_{sfx}(sig)
    local k1, k2, k3 = {{}}, {{}}, {{}}
    local acc = 0
    for i = 1, #sig do
        acc = (acc * 31 + sig:byte(i)) % 4294967296
        k1[i] = acc % 256
    end
    local idx = #sig + 1
    while idx <= 16 do
        acc = (acc * 31 + ((idx - 1) * 7)) % 4294967296
        k1[idx] = acc % 256; idx = idx + 1
    end
    local acc2 = 305419896
    for i = 1, #sig do
        acc2 = (acc2 * 17 + sig:byte(i) + 42) % 4294967296
        k2[i] = acc2 % 256
    end
    idx = #sig + 1
    while idx <= 16 do
        acc2 = (acc2 * 17 + (idx - 1)) % 4294967296
        k2[idx] = acc2 % 256; idx = idx + 1
    end
    for i = 1, 16 do k3[i] = _bxor_{sfx}(k1[i], k2[i]) end
    return k1, k2, k3
end

local _K1_{sfx}, _K2_{sfx}, _K3_{sfx} = _derive_{sfx}(_SIG_{sfx})
local _cache_{sfx} = {{}}
local _b64_{sfx} = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
local _b64map_{sfx} = {{}}
for i = 1, #_b64_{sfx} do _b64map_{sfx}[_b64_{sfx}:sub(i,i)] = i - 1 end

local _ENC_{sfx} = {{}}

local function _S_{sfx}(n)
    if _FAILED_{sfx} then return "" end
    if _cache_{sfx}[n] then return _cache_{sfx}[n] end
    local enc = _ENC_{sfx}[n]
    if not enc then return "" end
    local raw = {{}}; local acc, cnt = 0, 0
    for j = 1, #enc do
        local c = enc:sub(j,j)
        if c == "=" then break end
        local v = _b64map_{sfx}[c]
        if v then
            acc = acc + v * (64 ^ (3 - cnt)); cnt = cnt + 1
            if cnt == 4 then
                cnt = 0
                raw[#raw+1] = math.floor(acc/65536) % 256
                raw[#raw+1] = math.floor(acc/256) % 256
                raw[#raw+1] = acc % 256
                acc = 0
            end
        end
    end
    if cnt == 2 then raw[#raw+1] = math.floor(acc/65536) % 256
    elseif cnt == 3 then
        raw[#raw+1] = math.floor(acc/65536) % 256
        raw[#raw+1] = math.floor(acc/256) % 256
    end
    local n2 = #raw
    for i = 1, n2 do
        raw[i] = _bxor_{sfx}(raw[i], (i - 1) % 256 + 1)
        raw[i] = _bxor_{sfx}(raw[i], _K3_{sfx}[((i - 1) % 16) + 1])
    end
    for i = 1, n2 do
        raw[i] = _bxor_{sfx}(raw[i], _K2_{sfx}[((i - 1) % 16) + 1])
    end
    for i = 1, n2 do
        raw[i] = _bxor_{sfx}(raw[i], _K1_{sfx}[((i - 1) % 16) + 1])
    end
    local s = ""
    for i = 1, n2 do s = s .. string.char(raw[i]) end
    _cache_{sfx}[n] = s
    return s
end

if not _verify_{sfx}() then
    error("Sskid v2: integrity check failed", 0)
end
'''

    def _string_table(self):
        if not self.strings:
            return "for _i_ in ipairs({}) do end\n"
        parts = ",".join(f'"{s}"' for s in self.strings)
        return f"_ENC_{self.suffix} = {{{parts}}}\n"

    def _dead(self):
        blocks = []
        for _ in range(3):
            v1 = f"_d{random.randint(1000, 9999)}"
            v2 = f"_d{random.randint(1000, 9999)}"
            n1 = random.randint(100, 900)
            n2 = random.randint(1000, 9000)
            blocks.append(
                f"do local {v1}={n1}+{n2}; local {v2}={v1}*3-{n1}; "
                f"if {v2}>99999999 then {v2}=0 end end"
            )
        return "\n".join(blocks) + "\n"

    def obfuscate(self):
        body = self._transform()
        region = self._prologue() + self._string_table() + self._dead() + body
        h = self._hash(region)
        header = (
            "-- ═══════════════════════════════════════════════════\n"
            "-- Sskid Obfuscator v2 (final)\n"
            f"-- SIG: {self.sig}\n"
            f"-- HASH: {h}\n"
            "-- ⚠ Header must be intact; script verifies itself\n"
            "-- ═══════════════════════════════════════════════════\n"
        )
        return header + "--<<SKV2_START>>\n" + region + "\n--<<SKV2_END>>\n"

# ═══════════════════════════════════════════════════
#  KIVY UI
# ═══════════════════════════════════════════════════

BG      = get_color_from_hex('#0f0f14')
PANEL   = get_color_from_hex('#16161e')
ELEMENT = get_color_from_hex('#20202c')
ACCENT  = get_color_from_hex('#00aaff')
TEXT    = get_color_from_hex('#ebeef5')
DIM     = get_color_from_hex('#8a8a99')
SUCCESS = get_color_from_hex('#00c864')
ERROR   = get_color_from_hex('#ff3c50')

class SskidApp(App):
    title = 'Sskid Obfuscator'

    def build(self):
        Window.clearcolor = BG

        root = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(8))

        # ── Title bar ──
        title_bar = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
        title = Label(
            text='[b]SSKID[/b] OBFUSCATOR',
            markup=True,
            color=ACCENT,
            font_size=dp(18),
            halign='left',
            size_hint_x=0.7,
        )
        title.bind(size=title.setter('text_size'))
        title_bar.add_widget(title)

        clear_btn = Button(
            text='🗑',
            size_hint_x=0.15,
            background_color=ELEMENT,
            color=TEXT,
            font_size=dp(18),
        )
        clear_btn.bind(on_press=self.clear_all)
        title_bar.add_widget(clear_btn)

        root.add_widget(title_bar)

        # ── Input ──
        root.add_widget(Label(
            text='INPUT · paste Lua script',
            color=DIM, font_size=dp(11),
            size_hint_y=None, height=dp(20),
            halign='left',
        ))
        self.input_box = TextInput(
            text='',
            hint_text='Paste your Lua script here...',
            background_color=PANEL,
            foreground_color=TEXT,
            cursor_color=ACCENT,
            font_size=dp(13),
            multiline=True,
            size_hint_y=0.4,
        )
        root.add_widget(self.input_box)

        # ── Obfuscate button ──
        self.run_btn = Button(
            text='▶  OBFUSCATE',
            size_hint_y=None,
            height=dp(50),
            background_color=ACCENT,
            color=BG,
            font_size=dp(15),
            bold=True,
        )
        self.run_btn.bind(on_press=self.run_obfuscate)
        root.add_widget(self.run_btn)

        # ── Output ──
        out_header = BoxLayout(size_hint_y=None, height=dp(24), spacing=dp(4))
        out_header.add_widget(Label(
            text='OUTPUT · obfuscated',
            color=DIM, font_size=dp(11),
            halign='left',
            size_hint_x=0.6,
        ))
        copy_btn = Button(
            text='📋 Copy',
            size_hint_x=0.4,
            background_color=ELEMENT,
            color=ACCENT,
            font_size=dp(11),
        )
        copy_btn.bind(on_press=self.copy_output)
        out_header.add_widget(copy_btn)
        root.add_widget(out_header)

        self.output_box = TextInput(
            text='',
            background_color=PANEL,
            foreground_color=TEXT,
            font_size=dp(12),
            multiline=True,
            readonly=True,
            size_hint_y=0.4,
        )
        root.add_widget(self.output_box)

        # ── Status ──
        self.status = Label(
            text='Ready',
            color=DIM,
            font_size=dp(11),
            size_hint_y=None,
            height=dp(24),
            halign='left',
        )
        self.status.bind(size=self.status.setter('text_size'))
        root.add_widget(self.status)

        return root

    def _set_status(self, msg, kind='info'):
        colors = {'info': DIM, 'ok': SUCCESS, 'err': ERROR}
        self.status.text = msg
        self.status.color = colors.get(kind, DIM)

    def run_obfuscate(self, *_):
        src = self.input_box.text
        if not src or not src.strip():
            self._set_status('⚠ input is empty', 'err')
            return
        self.run_btn.text = 'running...'
        self._set_status('obfuscating...', 'info')
        try:
            obf = SskidV2(src)
            out = obf.obfuscate()
            self.output_box.text = out
            self._set_status(
                f'✓ {len(obf.strings)} strings encrypted · '
                f'{len(src):,} → {len(out):,} bytes',
                'ok'
            )
        except Exception as e:
            self._set_status(f'✕ error: {e}', 'err')
        finally:
            self.run_btn.text = '▶  OBFUSCATE'

    def copy_output(self, *_):
        if not self.output_box.text:
            self._set_status('⚠ nothing to copy', 'err')
            return
        try:
            Clipboard.copy(self.output_box.text)
            self._set_status('✓ copied to clipboard', 'ok')
        except Exception as e:
            self._set_status(f'✕ clipboard error: {e}', 'err')

    def clear_all(self, *_):
        self.input_box.text = ''
        self.output_box.text = ''
        self._set_status('cleared', 'info')

if __name__ == '__main__':
    SskidApp().run()
