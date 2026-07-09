const AXML = (() => {
  const VERSION = "1.1.0";
  const CHUNK_STRING_POOL = 0x0001;
  const CHUNK_START_TAG   = 0x0102;
  const CHUNK_END_TAG     = 0x0103;

  function u16(d, o) { return (d[o] | (d[o + 1] << 8)) >>> 0; }

  function u32(d, o) {
    return (d[o] | (d[o + 1] << 8) | (d[o + 2] << 16) | (d[o + 3] << 24)) >>> 0;
  }

  function parseStrPool(d, o) {
    var start = o;
    if (u16(d, o) !== CHUNK_STRING_POOL) { console.log("[axml] not a string pool chunk at offset", o.toString(16)); return [[], o + 8]; }
    var hdrSize = u16(d, o + 2);
    var chunkSz = u32(d, o + 4);
    var strCnt  = u32(d, o + 8);
    var styCnt  = u32(d, o + 12);
    var flags   = u32(d, o + 16);
    var strOff  = u32(d, o + 20);
    var styOff  = u32(d, o + 24);
    var utf8    = (flags & 0x100) !== 0;
    var tbl     = [];

    console.log("[axml] string pool: count=" + strCnt + " styles=" + styCnt + " utf8=" + utf8 + " chunkSz=" + chunkSz);

    var p = start + hdrSize;
    var strIdx = [];
    for (var i = 0; i < strCnt; i++) { strIdx.push(u32(d, p)); p += 4; }
    if (styCnt > 0) { p += styCnt * 4; }

    for (var i = 0; i < strCnt; i++) {
      var sp = start + strOff + strIdx[i];
      var s;
      if (utf8) {
        var bc = d[sp], cc = d[sp + 1];
        if (bc >= 0x80) { bc = u32(d, sp + 1); cc = u32(d, sp + 5); sp += 8; }
        else { sp += 2; }
        var end = sp;
        while (end < d.length && d[end] !== 0) end++;
        s = new TextDecoder("utf-8").decode(d.slice(sp, end));
      } else {
        var cn = u16(d, sp);
        sp += 2;
        s = new TextDecoder("utf-16le").decode(d.slice(sp, sp + cn * 2));
      }
      tbl.push(s || "");
    }

    console.log("[axml] first 20 strings:", tbl.slice(0, 20).map(function(x){return JSON.stringify(x);}).join(", "));
    return [tbl, start + chunkSz];
  }

  function parseTag(d, o, str, res) {
    if (u16(d, o) !== CHUNK_START_TAG) return;
    var nameIdx = u32(d, o + 20);
    var name = str[nameIdx] || "";
    if (name.toLowerCase() !== "manifest") return;

    console.log("[axml] found <manifest> tag at offset", o.toString(16));

    var hdrSize  = u16(d, o + 2);
    var attrStart = u16(d, o + 24);
    var attrSize  = u16(d, o + 26);
    var attrCnt   = u16(d, o + 28);
    console.log("[axml] manifest hdrSize=" + hdrSize + " attrStart=" + attrStart + " attrSize=" + attrSize + " attrCnt=" + attrCnt);

    var ap = o + hdrSize + attrStart;
    for (var i = 0; i < attrCnt; i++) {
      var ans = u32(d, ap);
      var an  = str[u32(d, ap + 4)] || "";
      var rv  = u32(d, ap + 8);
      var vSize = u16(d, ap + 12);
      var vt   = d[ap + 15];
      var vd   = u32(d, ap + 16);
      var val;
      if (vt === 0x03) val = str[rv] || "";
      else if (vt === 0x10) val = vd;
      else if (vt === 0x11 || vt === 0x01) val = (vd === 0 || vd === 0xFFFFFFFF) ? "false" : "true";
      else val = vd;

      console.log("[axml]   attr[" + i + "] nsIdx=" + ans + " name=" + JSON.stringify(an) + " type=0x" + vt.toString(16) + " val=" + JSON.stringify(val) + " (rv=" + rv + " vd=" + vd + ")");

      if (an === "package") res.package = String(val);
      if (an === "versionCode") res.versionCode = Number(val);
      if (an === "versionName") res.versionName = String(val);
      if (an === "label") res.label = String(val);
      ap += attrSize;
    }
  }

  function parse(data) {
    var res = { package: "", versionCode: 0, versionName: "", label: "" };
    var magic = u32(data, 0);
    console.log("[axml] magic=0x" + magic.toString(16) + " dataLen=" + data.length);
    if (magic !== 0x00080003) { console.log("[axml] INVALID MAGIC"); return res; }
    var sz = u32(data, 4);
    console.log("[axml] fileSize=" + sz);
    var str = [];
    var o = 8;
    while (o + 8 <= data.length && o < sz) {
      var ct = u16(data, o);
      var cs = u32(data, o + 4);
      console.log("[axml] chunk at 0x" + o.toString(16) + " type=0x" + ct.toString(16) + " size=" + cs);
      if (ct === CHUNK_STRING_POOL) { var r = parseStrPool(data, o); str = r[0]; o = r[1]; }
      else if (ct === CHUNK_START_TAG) { parseTag(data, o, str, res); o += cs; }
      else { o += cs || 8; }
    }
    console.log("[axml] result:", JSON.stringify(res));
    return res;
  }

  return { VERSION: VERSION, parse: parse };
})();

if (typeof module !== "undefined") module.exports = AXML;
