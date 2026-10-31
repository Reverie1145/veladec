// app.jsc
// decompiled by veladec 1.0.0 -- pseudo-JS, goto-preserving
// --- module entry: fn[entry] $k82(a0..a0) vars=0 stack=1 bc=13B
    if (this) {
        v0 = <fn:default>;
        return;
    }
L000c:
    return;

// --- fn[36] decode(a0..a0) vars=6 stack=5 bc=227B
    r3 = undefined;
    r2 = undefined;
    r1 = undefined;
    r0 = undefined;
    if (a0) goto L0017;
L0017:
    r0 = (((a0("")).replace(/-/, "+")).replace(/_/, "/")).replace(/=+$/, "");
    r1 = [];
    r2 = 0;
    r3 = 0;
    r4 = undefined;
    r4 = 0;
L0059:
    while (r4 < r0.length) {
        r5 = undefined;
        r5 = v0.indexOf(r0.charAt(r4));
        if (r5 < 0) {
            return null;
        }
    L008a:
        r3 = r3 << 6 | r5;
        r2 = r2 + 6;
        if (r2 >= 8) {
            r2 = r2 - 8;
        }
    L00cc:
        r4++;
    }
L00d6:
    return new Uint8Array(r1);
