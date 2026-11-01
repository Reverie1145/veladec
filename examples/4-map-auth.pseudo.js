// auto-selected 2020-11-08 (penalty: 2019-07-09=5985, 2019-12-21=7932, 2020-01-19=7932, 2020-07-05=2125, 2020-11-08=0, 2021-03-27=0)
// pages/auth/auth.jsc
// decompiled by veladec 1.1.0 -- pseudo-JS, goto-preserving
// --- module entry: fn[entry] $k82(a0..a0) vars=0 stack=1 bc=13B
    if (this) {
        v0 = <fn:default>;
        return;
    }
L000c:
    return;

// --- fn[0] _interopRequireDefault(a0..a0) vars=0 stack=2 bc=21B
    if (!(a0)) goto L000d;
    if (!(a0.__esModule)) goto L000d;
    return a0;
L000d:   // 2 refs
    return {default: a0};

// --- fn[1] <null>(a0..a0) vars=2 stack=4 bc=165B
    if (!a0) {
    L001a:
        return;
    }
L001b:
    // try {  (catch at L0088)
    r0 = undefined;
    r0 = JSON.parse(a0);
    if (!r0) goto L006f;
    if ("string" != typeof r0.phase) goto L006f;
    if ("string" != typeof r0.request) goto L006f;
L006f:   // 3 refs
    if ("number" != typeof r0.revision) {
        throw new Error("Invalid state");
    }
L0080:
    return;
    // } catch (exc27) {  (try at L001b)
L0088:
    r1 = exc27;
    // catch (handler -> L001a)
    return;
    throw "string" != typeof r0.phase;
    return !r0;

// --- fn[2] <null>(a0..a0) vars=0 stack=3 bc=21B
    return v0({phase: "blocked", request: ""});

// --- fn[3] state(a0..a0) vars=0 stack=4 bc=54B
    return;

// --- fn[4] <null>(a0..a0) vars=0 stack=2 bc=5B
    return v0(true);

// --- fn[5] <null>(a0..a0) vars=0 stack=2 bc=5B
    return v0(false);

// --- fn[6] save(a0..a2) vars=0 stack=7 bc=95B
    return;

// --- fn[7] enqueue(a0..a1) vars=0 stack=4 bc=28B
    return;

// --- fn[8] <null>(a0..a0) vars=0 stack=4 bc=56B
    if (v0) {
    L0005:
        return;
    }
L0006:
    v0 = true;
L000c:
    v1 = false;
    // try {  (catch at L001a)
    // } catch (exc18) {  (try at L0012)
L001a:
    gosub L000c;
    return;
    gosub L0005;
    throw ?;
    return;
    return;

// --- fn[9] drain(a0..a0) vars=4 stack=4 bc=89B
    r2 = undefined;
    r1 = undefined;
    r0 = undefined;
L000c:
    if (v0) goto L0015;
L0015:   // 2 refs
    if (!v2.length) {
        return;
    }
L0018:
    v0 = true;
    r0 = v2.shift();
    r1 = false;
    r2 = <fn:finish>;
    // catch (handler -> L0015)
    return;
    r3 = ?;
    // catch (handler -> L000c)
    return;
    throw ?;

// --- fn[10] valid(a0..a1) vars=0 stack=4 bc=146B
    if (!a0) goto L0087;
    if (true !== a0.direct) goto L0087;
    if (a0.request) goto L002a;
L002a:
    if (!a0.request.test("")) goto L0087;
    if ("number" != typeof a0.revision) goto L0087;
    if (!isFinite(a0.revision)) goto L0087;
    if (a0.revision <= 0) goto L0087;
    if (a0.revision > 9007199254740991) goto L0087;
L0087:   // 7 refs
    if (Math.floor(a0.revision) !== a0.revision) {
        return;
    }
L008e:
    return;

// --- fn[11] <null>(a0..a0) vars=0 stack=4 bc=11B
    return v0("reset", v1, v2);

// --- fn[12] <null>(a0..a0) vars=0 stack=2 bc=5B
    return v0(false);

// --- fn[13] <null>(a0..a0) vars=0 stack=4 bc=56B
    return;

// --- fn[14] <null>(a0..a0) vars=0 stack=2 bc=5B
    return v0(false);

// --- fn[15] <null>(a0..a0) vars=0 stack=4 bc=69B
    if (!a0) {
        return;
    }
L0009:
    return;

// --- fn[16] <null>(a0..a0) vars=1 stack=4 bc=222B
    r0 = undefined;
    if (a0.revision) goto L0014;
L0014:
    if (a0.revision < 0) goto L0035;
    if (v1.revision !== a0.revision) goto L003c;
L0035:
    if (a0.request === v1.request) goto L003c;
    return;
L003c:   // 2 refs
    if ("manual-reset" !== a0.phase) goto L0072;
    if (v1.revision <= a0.revision) goto L006b;
    if (!(v1.active)) goto L0072;
L006b:
    if (true === v1.explicit) goto L0072;
    return;
L0072:   // 3 refs
    if (v1.active) {
    } else {
    }
L0086:
    r0 = "active";
    if (a0.request !== v1.request) goto L00c0;
    if (a0.phase === r0) goto L00b9;
    if (!(!v1.active)) goto L00c0;
L00b9:
    if ("banned" !== a0.phase) goto L00c0;
    return;
L00c0:   // 3 refs
    if (v1.active) {
        return;
    }
L00d3:
    return;

// --- fn[17] <null>(a0..a0) vars=0 stack=2 bc=33B
    if (!a0) goto L0013;
L0013:
    if ("boolean" != typeof v1.active) {
        return;
    }
L001a:
    return;

// --- fn[18] <null>(a0..a0) vars=0 stack=3 bc=9B
    return v4(v1, <fn:<null>>);

// --- fn[19] $k92(a0..a1) vars=0 stack=3 bc=8B
    return;

// --- fn[20] <null>(a0..a0) vars=0 stack=2 bc=5B
    return v0(true);

// --- fn[21] <null>(a0..a0) vars=0 stack=2 bc=5B
    return v0(false);

// --- fn[22] <null>(a0..a0) vars=0 stack=4 bc=56B
    return;

// --- fn[23] <null>(a0..a0) vars=0 stack=2 bc=5B
    return v0(false);

// --- fn[24] <null>(a0..a0) vars=0 stack=4 bc=69B
    if (!a0) {
        return;
    }
L0009:
    return;

// --- fn[25] <null>(a0..a0) vars=0 stack=5 bc=43B
    if (a0.request) goto L0012;
L0012:
    a0.request.request = "";
    if (a0.revision) goto L0022;
L0022:
    a0.revision.revision = 0;
    return;

// --- fn[26] <null>(a0..a0) vars=0 stack=2 bc=6B
    return v2(<fn:<null>>);

// --- fn[27] manualReset(a0..a0) vars=0 stack=3 bc=6B
    return;

// --- fn[28] <null>(a0..a0) vars=0 stack=4 bc=96B
    if (a0.request !== v0.request) goto L003c;
    if (a0.revision !== v0.revision) goto L003c;
    if ("reset" === a0.phase) goto L0043;
L003c:   // 2 refs
    if ("banned" === a0.phase) goto L0043;
    return;
L0043:   // 2 refs
    if ("banned" === a0.phase) {
        return;
    }
L0056:
    return;

// --- fn[29] <null>(a0..a0) vars=0 stack=2 bc=14B
    if (!a0) {
        return;
    }
L0009:
    return;

// --- fn[30] <null>(a0..a0) vars=0 stack=3 bc=7B
    return v3(v0, <fn:<null>>);

// --- fn[31] notice(a0..a1) vars=0 stack=3 bc=6B
    return;

// --- fn[32] <null>(a0..a0) vars=13 stack=3 bc=103B
    r1 = <fn:_interopRequireDefault>;
    r5 = <fn:state>;
    r6 = <fn:save>;
    r7 = <fn:enqueue>;
    r8 = <fn:drain>;
    r9 = <fn:valid>;
    r10 = <fn:$k92>;
    r11 = <fn:manualReset>;
    r12 = <fn:notice>;
    r4 = undefined;
    r3 = undefined;
    r2 = undefined;
    r0 = r1(v0("@app-module/system.storage"));
    r2 = "phoneOrderActivation";
    r3 = false;
    r4 = [];
    {state: r5, $k92: r10, notice: r12, manualReset: r11}.exports = a0;
    return;

// --- fn[33] getVib(a0..a0) vars=1 stack=3 bc=55B
    if (v0) {
        return v1;
    }
L0009:
    v0 = true;
    // try {  (catch at L0023)
    v1 = v2("@app-module/system.vibrator");
    goto L0033;
    // } catch (exc15) {  (try at L000f)
L0023:
    r0 = exc15;
    // try {  (catch at L0032)
    v1 = null;
    goto L0033;
    // } catch (exc36) {  (try at L0024)
L0032:
    throw exc36;
L0033:   // 2 refs
    return v1;

// --- fn[34] <null>(a0..a0) vars=1 stack=5 bc=35B
    // try {  (catch at L0019)
    // } catch (exc0) {  (try at L0000)
L0019:
    return;
    r0 = exc0;
    // try {  (catch at L0022)
    return;
    // } catch (exc27) {  (try at L001b)
L0022:
    throw exc27;

// --- fn[35] <null>(a0..a0) vars=0 stack=2 bc=11B
    return v0("short");

// --- fn[36] <null>(a0..a0) vars=0 stack=2 bc=11B
    return v0("short");

// --- fn[37] <null>(a0..a0) vars=0 stack=2 bc=11B
    return v0("short");

// --- fn[38] buzz(a0..a0) vars=4 stack=4 bc=131B
    r2 = undefined;
    r1 = undefined;
    r0 = undefined;
    r0 = v0();
    if (!r0) {
        return;
    }
L0013:
    if (a0) goto L001d;
L001d:
    r1 = "short";
    r2 = <fn:fire>;
    if ("long" === r1) {
        return;
    }
L004b:
    r3 = undefined;
    r3 = 0;
L0050:
    while (r3 < v2) {
        if (0 === r3) {
        } else {
        }
    L0078:
        r3++;
    }
L0082:
    return;

// --- fn[39] <null>(a0..a0) vars=1 stack=5 bc=39B
    // try {  (catch at L001d)
    // } catch (exc0) {  (try at L0000)
L001d:
    return;
    r0 = exc0;
    // try {  (catch at L0026)
    return;
    // } catch (exc31) {  (try at L001f)
L0026:
    throw exc31;

// --- fn[40] buzzStrong(a0..a1) vars=5 stack=5 bc=121B
    r2 = undefined;
    r1 = undefined;
    r0 = undefined;
    r0 = v0();
    if (!r0) {
        return;
    }
L0013:
    if (a0) goto L0019;
L0019:
    r1 = 4;
    if (a1) goto L0022;
L001e:
L0022:
    r2 = v1;
    r3 = undefined;
    r3 = 0;
L0028:
    while (r3 < r1) {
        if (0 === r3) {
            // catch (handler -> L001e)
            goto L006e;
            r4 = a0;
            // try {  (catch at L0061)
            goto L006e;
            // } catch (exc89) {  (try at L0059)
        L0061:
            throw exc89;
        }
    L0062:
    L006e:   // 2 refs
        r3++;
    }
L0078:
    return;

// --- fn[41] <null>(a0..a1) vars=7 stack=6 bc=77B
    r2 = <fn:getVib>;
    r5 = <fn:buzz>;
    r6 = <fn:buzzStrong>;
    r4 = undefined;
    r3 = undefined;
    r1 = undefined;
    r0 = undefined;
    r5.buzz = a1;
    r6.buzzStrong = a1;
    r0 = null;
    r1 = false;
    r3 = 3;
    r4 = 110;
    return;

// --- fn[42] __webpack_require__(a0..a0) vars=2 stack=5 bc=51B
    r0 = v0[a0];
    if (undefined !== r0) {
        return r0.exports;
    }
L0010:
    v0[a0] = {exports: {}};
    r1 = {exports: {}};
    return r1.exports;

// --- fn[43] <null>(a0..a0) vars=0 stack=1 bc=6B
    return "1.7.12";

// --- fn[44] <null>(a0..a0) vars=0 stack=2 bc=9B
    <fn:<null>>.rv = v0;
    return;

// --- fn[45] <null>(a0..a0) vars=0 stack=2 bc=12B
    "bundler=rspack@1.7.12".ruid = v0;
    return;

// --- fn[46] _interopRequireDefault(a0..a0) vars=0 stack=2 bc=21B
    if (!(a0)) goto L000d;
    if (!(a0.__esModule)) goto L000d;
    return a0;
L000d:   // 2 refs
    return {default: a0};

// --- fn[47] <null>(a0..a0) vars=0 stack=3 bc=71B
    if ("banned" === a0) {
    } else {
        if ("订单已被封禁，手环已取消激活" === a0) {
        } else {
            if ("已手动重置，请在手机重新提交激活" === a0) goto L0033;
        L0033:
            if ("revoking" === a0) {
            } else {
            }
        }
    }
L0041:   // 3 refs
    "正在等待手机同步使用状态…".statusText = "已手动重置，请在手机重新提交激活" === a0;
    return;

// --- fn[48] <null>(a0..a0) vars=0 stack=3 bc=15B
    return v0._orderStatusListener(a0.phase);

// --- fn[49] <null>(a0..a0) vars=0 stack=4 bc=30B
    if (a0) {
    }
L001d:
    return;

// --- fn[50] <null>(a0..a0) vars=2 stack=4 bc=125B
    r1 = this;
    // try {  (catch at L001b)
L0007:
    // } catch (exc2) {  (try at L0002)
L001b:
    goto L0028;
    r0 = ?;
    // catch (handler -> L0007)
    goto L0028;
    throw ?;
L0028:   // 2 refs
    <fn:<null>>._orderStatusListener = r1;
    r1._orderStatusListener.orderStatusListener = r1.$app.$def;
    return;

// --- fn[51] <null>(a0..a0) vars=1 stack=2 bc=45B
    r0 = this;
    if (r0.$app.$def.orderStatusListener === r0._orderStatusListener) {
        null.orderStatusListener = r0.$app.$def;
    }
L002c:
    return;

// --- fn[52] <null>(a0..a0) vars=1 stack=2 bc=18B
    r0 = this;
    true.showQr = r0;
    return;

// --- fn[53] <null>(a0..a0) vars=1 stack=2 bc=18B
    r0 = this;
    false.showQr = r0;
    return;

// --- fn[54] <null>(a0..a0) vars=0 stack=2 bc=23B
    return;

// --- fn[55] <null>(a0..a0) vars=0 stack=2 bc=6B
    return v0[a0];

// --- fn[56] <null>(a0..a0) vars=2 stack=6 bc=132B
    r0 = undefined;
    r0 = typeof v0[a0];
    if ("$k75" === r0) {
        Object.assign(v0.data, v0[a0]).data = v0;
        r1 = undefined;
        goto L0057;
    L0042:
        r1 = ?;
        v0._descriptor[r1] = {access: a0};
    L0057:
        if (!(__iter(v0[a0]).done)) goto L0042;
        return;
    }
L005d:
    if ("object" === r0) {
    }
L0083:
    return;

// --- fn[57] __scriptModule__(a0..a2) vars=8 stack=6 bc=302B
    r4 = <fn:_interopRequireDefault>;
    r7 = undefined;
    r6 = undefined;
    undefined.default = a1;
    r0 = r4(a2("@app-module/system.router"));
    r1 = r4(a2("@app-module/system.app"));
    r2 = r4(v0("./src/Common/order-activation.js"));
    r3 = v0("./src/Common/ui.js");
    {data: {statusText: "等待手机发送激活指令", showQr: false}}.onShow = <fn:<null>>;
    {data: {statusText: "等待手机发送激活指令", showQr: false}}.onHide = <fn:<null>>;
    {data: {statusText: "等待手机发送激活指令", showQr: false}}.openQr = <fn:<null>>;
    {data: {statusText: "等待手机发送激活指令", showQr: false}}.closeQr = <fn:<null>>;
    {data: {statusText: "等待手机发送激活指令", showQr: false}}.exitApp = <fn:<null>>;
    a1.default = {data: {statusText: "等待手机发送激活指令", showQr: false}};
    r5 = a1;
    if (a1.default) goto L00ad;
L00ad:
    r6 = a0.exports;
    r7 = ["$k45", "$k44", "$k43"];
    if (!(r6.data)) goto L0102;
    if (!(r7.some(<fn:<null>>))) goto L0102;
    throw new Error(("页面VM对象中的属性data不可与\"" + r7.$k93(",")) + "\"同时存在，请使用private替换data名称");
L0102:   // 2 refs
    if (!r6.data) {
        {}.data = r6;
        {}._descriptor = r6;
    }
L012d:
    return;

// --- fn[58] <null>(a0..a0) vars=0 stack=3 bc=12B
    return v0.exitApp(a0);

// --- fn[59] <null>(a0..a0) vars=0 stack=3 bc=12B
    return v0.openQr(a0);

// --- fn[60] <null>(a0..a0) vars=0 stack=1 bc=9B
    return v0.statusText;

// --- fn[61] <null>(a0..a0) vars=0 stack=1 bc=9B
    return v0.showQr;

// --- fn[62] <null>(a0..a0) vars=0 stack=3 bc=12B
    return v0.closeQr(a0);

// --- fn[63] <null>(a0..a0) vars=0 stack=21 bc=405B
    return [aiot.__ce__("div", {__vm__: v0, __opts__: {classList: ["overlay"]}}, [aiot.__ce__("div", {__vm__: v0, __opts__: {classList: ["qr-box"]}}, [aiot.__ce__("text", {__vm__: v0, __opts__: {classList: ["qr-title"], state: "下载手机安装包"}}, []), aiot.__ce__("image", {__vm__: v0, __opts__: {classList: ["qr-img"], src: "/Common/afdian-download.png"}}, []), aiot.__ce__("text", {__vm__: v0, __opts__: {classList: ["qr-hint"], state: "用手机扫码下载 APK"}}, []), aiot.__ce__("div", {__vm__: v0, __opts__: {classList: ["qr-close"], events: {click: <fn:click>}}}, [aiot.__ce__("text", {__vm__: v0, __opts__: {classList: ["qr-close-t"], state: "关闭"}}, [])])])])];

// --- fn[64] <null>(a0..a0) vars=2 stack=19 bc=809B
    r1 = this;
    r0 = undefined;
    if (a0) goto L000b;
L000b:
    r0 = r1;
    return aiot.__ce__("div", {__vm__: r0, __opts__: {classList: ["page"]}}, [aiot.__ce__("div", {__vm__: r0, __opts__: {classList: ["topbar"]}}, [aiot.__ce__("text", {__vm__: r0, __opts__: {classList: ["title-l"], state: "离线地图·激活"}}, []), aiot.__ce__("div", {__vm__: r0, __opts__: {classList: ["exit-btn"], events: {click: <fn:click>}}}, [aiot.__ce__("text", {__vm__: r0, __opts__: {classList: ["exit-ic"], state: "×"}}, [])])]), aiot.__ce__("div", {__vm__: r0, __opts__: {classList: ["code-box"]}}, [aiot.__ce__("text", {__vm__: r0, __opts__: {classList: ["code-label"], state: "手机直接激活"}}, []), aiot.__ce__("text", {__vm__: r0, __opts__: {classList: ["code-value"], state: "无需设备码"}}, [])]), aiot.__ce__("text", {__vm__: r0, __opts__: {classList: ["instruction"], state: "请在手机 App 中输入爱发电订单号完成激活"}}, []), aiot.__ce__("text", {__vm__: r0, __opts__: {classList: ["hint"], state: "手机和手环保持连接，激活后会自动同步到手环。"}}, []), aiot.__ce__("div", {__vm__: r0, __opts__: {classList: ["download-btn"], events: {click: <fn:click>}}}, [aiot.__ce__("text", {__vm__: r0, __opts__: {classList: ["download-btn-t"], state: "扫码下载手机安装包"}}, [])]), aiot.__ce__("text", {__vm__: r0, __opts__: {classList: ["$k138"], state: <fn:state>}}, []), aiot.__ci__({__vm__: r0, __opts__: {shown: <fn:shown>}}, <fn:<null>>)]);

// --- fn[65] <null>(a0..a0) vars=0 stack=4 bc=31B
    v2.template = a0.default;
    v3.style = a0.default;
    return;

// --- fn[66] <null>(a0..a0) vars=3 stack=22 bc=1366B
    r0 = [[[[0, "page"]], {width: "100%", height: "100%", flexDirection: "column", backgroundColor: "#080d11", paddingTop: "10px", paddingRight: "10px", paddingBottom: "10px", paddingLeft: "10px"}], [[[0, "topbar"]], {flexDirection: "row", alignItems: "center", height: "52px", marginTop: "2px"}], [[[0, "title-l"]], {color: "#ffffff", fontSize: "22px", fontWeight: "bold", flex: 1, textAlign: "left"}], [[[0, "exit-btn"]], {width: "52px", height: "52px", backgroundColor: "#172126", borderRadius: "26px", justifyContent: "center", alignItems: "center"}], [[[0, "exit-ic"]], {color: "#ffffff", fontSize: "30px", fontWeight: "bold"}], [[[0, "code-box"]], {backgroundColor: "#172126", borderRadius: "18px", paddingTop: "12px", paddingRight: "12px", paddingBottom: "12px", paddingLeft: "12px", marginTop: "12px", flexDirection: "column", alignItems: "center"}], [[[0, "code-label"]], {color: "#a7b8bf", fontSize: "16px"}], [[[0, "code-value"]], {color: "#2dd4bf", fontSize: "24px", letterSpacing: "2px", marginTop: "6px"}], [[[0, "instruction"]], {color: "#ffffff", fontSize: "19px", textAlign: "center", marginTop: "24px", lineHeight: "27px"}], [[[0, "hint"]], {color: "#a7b8bf", fontSize: "15px", textAlign: "center", marginTop: "12px", lineHeight: "21px"}], [[[0, "download-btn"]], {width: "272px", height: "50px", backgroundColor: "#087f75", borderRadius: "24px", justifyContent: "center", alignItems: "center", marginTop: "25px", alignSelf: "center"}], [[[0, "download-btn-t"]], {color: "#ffffff", fontSize: "17px", fontWeight: "bold"}], [[[0, "$k138"]], {color: "#a7b8bf", fontSize: "14px", textAlign: "center", marginTop: "14px"}], [[[0, "overlay"]], {position: "absolute", left: 0, top: 0, right: 0, bottom: 0, backgroundColor: "rgba(0, 0, 0, 0.84)", justifyContent: "center", alignItems: "center"}], [[[0, "qr-box"]], {width: "300px", backgroundColor: "#172126", borderRadius: "24px", paddingTop: "14px", paddingRight: "14px", paddingBottom: "14px", paddingLeft: "14px", alignItems: "center", flexDirection: "column"}], [[[0, "qr-title"]], {color: "#ffffff", fontSize: "20px", fontWeight: "bold", textAlign: "center", marginBottom: "10px"}], [[[0, "qr-img"]], {width: "216px", height: "216px"}], [[[0, "qr-hint"]], {color: "#a7b8bf", fontSize: "15px", textAlign: "center", marginTop: "8px"}], [[[0, "qr-close"]], {width: "180px", height: "48px", backgroundColor: "#087f75", borderRadius: "24px", justifyContent: "center", alignItems: "center", marginTop: "12px"}], [[[0, "qr-close-t"]], {color: "#ffffff", fontSize: "19px", fontWeight: "bold"}]];
    r1 = <fn:__scriptModule__>;
    r2 = <fn:$app_template$>;
    v2["entry"] = <fn:<null>>;
    return;

// --- fn[67] <null>(a0..a0) vars=4 stack=2 bc=37B
    r2 = <fn:__webpack_require__>;
    {}../src/Common/order-activation.js = <fn:<null>>;
    {}../src/Common/ui.js = <fn:<null>>;
    r0 = {};
    r1 = {};
    r3 = {};
    return;

// --- fn[68] <null>(a0..a0) vars=0 stack=1 bc=5B
    return <fn:<null>>();

// --- fn[69] <null>(a0..a4) vars=6 stack=2 bc=53B
    r0 = a0.setTimeout;
    r1 = a0.setInterval;
    r2 = a0.clearTimeout;
    r3 = a0.clearInterval;
    if (a0.$app_require$) goto L0027;
L0027:
    r4 = v0;
    r5 = <fn:createPageHandler>;
    return <fn:createPageHandler>();

// --- fn[70] <null>(a0..a4) vars=1 stack=6 bc=19B
    r0 = $app_require$;
    return;

// --- fn[71] $k82(a0..a0) vars=0 stack=1 bc=13B
    if (this) {
        v0 = <fn:default>;
        return;
    }
L000c:
    return;
