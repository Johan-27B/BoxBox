#include <stdio.h>
#include <stdlib.h>

long func_0(long a, long b) {
    long r = a + b * 82;
    for (int i = 0; i < 13; i++) r += (r >> 3) + 251;
    long arr[44];
    for (int j = 0; j < 44; j++) arr[j] = r + j;
    for (int j = 0; j < 44; j++) r += arr[j];
    return r;
}

long func_1(long a, long b) {
    long r = a + b * 12;
    for (int i = 0; i < 64; i++) r += (r >> 1) + 31;
    for (int i = 0; i < 21; i++) r += (r >> 2) + 239;
    for (int i = 0; i < 74; i++) r += (r >> 5) + 28;
    if (r > 760800) r = r % 9028;
    return r;
}

long func_2(long a, long b) {
    long r = a + b * 58;
    for (int i = 0; i < 45; i++) r += (r >> 1) + 778;
    for (int i = 0; i < 30; i++) r += (r >> 4) + 349;
    for (int i = 0; i < 45; i++) r += (r >> 2) + 221;
    if (r > 362944) r = r % 1774;
    return r;
}

long func_3(long a, long b) {
    long r = a + b * 13;
    for (int i = 0; i < 54; i++) r += (r >> 5) + 271;
    for (int i = 0; i < 15; i++) r += (r >> 4) + 550;
    long arr[15];
    for (int j = 0; j < 15; j++) arr[j] = r + j;
    for (int j = 0; j < 15; j++) r += arr[j];
    return r;
}

long func_4(long a, long b) {
    long r = a + b * 71;
    for (int i = 0; i < 90; i++) r += (r >> 5) + 907;
    for (int i = 0; i < 56; i++) r += (r >> 5) + 197;
    if (r > 58050) r = r % 3833;
    long arr[15];
    for (int j = 0; j < 15; j++) arr[j] = r + j;
    for (int j = 0; j < 15; j++) r += arr[j];
    return r;
}

long func_5(long a, long b) {
    long r = a + b * 30;
    for (int i = 0; i < 58; i++) r += (r >> 3) + 465;
    if (r > 392554) r = r % 2764;
    return r;
}

long func_6(long a, long b) {
    long r = a + b * 27;
    for (int i = 0; i < 44; i++) r += (r >> 1) + 624;
    for (int i = 0; i < 91; i++) r += (r >> 2) + 547;
    for (int i = 0; i < 41; i++) r += (r >> 2) + 474;
    if (r > 980342) r = r % 9225;
    return r;
}

long func_7(long a, long b) {
    long r = a + b * 42;
    for (int i = 0; i < 39; i++) r += (r >> 1) + 825;
    if (r > 290746) r = r % 1184;
    return r;
}

long func_8(long a, long b) {
    long r = a + b * 73;
    for (int i = 0; i < 50; i++) r += (r >> 2) + 672;
    for (int i = 0; i < 73; i++) r += (r >> 4) + 906;
    for (int i = 0; i < 92; i++) r += (r >> 4) + 147;
    return r;
}

long func_9(long a, long b) {
    long r = a + b * 72;
    for (int i = 0; i < 43; i++) r += (r >> 5) + 439;
    for (int i = 0; i < 84; i++) r += (r >> 4) + 371;
    for (int i = 0; i < 38; i++) r += (r >> 2) + 522;
    if (r > 802495) r = r % 871;
    long arr[19];
    for (int j = 0; j < 19; j++) arr[j] = r + j;
    for (int j = 0; j < 19; j++) r += arr[j];
    return r;
}

long func_10(long a, long b) {
    long r = a + b * 81;
    for (int i = 0; i < 97; i++) r += (r >> 4) + 611;
    return r;
}

long func_11(long a, long b) {
    long r = a + b * 60;
    for (int i = 0; i < 42; i++) r += (r >> 5) + 882;
    for (int i = 0; i < 11; i++) r += (r >> 1) + 699;
    for (int i = 0; i < 78; i++) r += (r >> 3) + 788;
    if (r > 126970) r = r % 4908;
    return r;
}

long func_12(long a, long b) {
    long r = a + b * 59;
    for (int i = 0; i < 43; i++) r += (r >> 5) + 781;
    long arr[50];
    for (int j = 0; j < 50; j++) arr[j] = r + j;
    for (int j = 0; j < 50; j++) r += arr[j];
    return r;
}

long func_13(long a, long b) {
    long r = a + b * 39;
    for (int i = 0; i < 74; i++) r += (r >> 5) + 204;
    for (int i = 0; i < 29; i++) r += (r >> 3) + 781;
    for (int i = 0; i < 30; i++) r += (r >> 5) + 977;
    if (r > 566116) r = r % 109;
    long arr[41];
    for (int j = 0; j < 41; j++) arr[j] = r + j;
    for (int j = 0; j < 41; j++) r += arr[j];
    return r;
}

long func_14(long a, long b) {
    long r = a + b * 3;
    for (int i = 0; i < 56; i++) r += (r >> 3) + 246;
    long arr[15];
    for (int j = 0; j < 15; j++) arr[j] = r + j;
    for (int j = 0; j < 15; j++) r += arr[j];
    return r;
}

long func_15(long a, long b) {
    long r = a + b * 11;
    for (int i = 0; i < 72; i++) r += (r >> 1) + 779;
    for (int i = 0; i < 78; i++) r += (r >> 2) + 132;
    for (int i = 0; i < 94; i++) r += (r >> 4) + 970;
    if (r > 287932) r = r % 8745;
    long arr[37];
    for (int j = 0; j < 37; j++) arr[j] = r + j;
    for (int j = 0; j < 37; j++) r += arr[j];
    return r;
}

long func_16(long a, long b) {
    long r = a + b * 28;
    for (int i = 0; i < 98; i++) r += (r >> 2) + 731;
    for (int i = 0; i < 49; i++) r += (r >> 4) + 688;
    for (int i = 0; i < 93; i++) r += (r >> 3) + 449;
    if (r > 483417) r = r % 2082;
    return r;
}

long func_17(long a, long b) {
    long r = a + b * 9;
    for (int i = 0; i < 12; i++) r += (r >> 5) + 568;
    for (int i = 0; i < 39; i++) r += (r >> 5) + 226;
    long arr[13];
    for (int j = 0; j < 13; j++) arr[j] = r + j;
    for (int j = 0; j < 13; j++) r += arr[j];
    return r;
}

long func_18(long a, long b) {
    long r = a + b * 30;
    for (int i = 0; i < 14; i++) r += (r >> 3) + 73;
    if (r > 302004) r = r % 8053;
    return r;
}

long func_19(long a, long b) {
    long r = a + b * 17;
    for (int i = 0; i < 83; i++) r += (r >> 5) + 485;
    for (int i = 0; i < 41; i++) r += (r >> 4) + 827;
    for (int i = 0; i < 62; i++) r += (r >> 2) + 97;
    return r;
}

long func_20(long a, long b) {
    long r = a + b * 55;
    for (int i = 0; i < 69; i++) r += (r >> 1) + 690;
    for (int i = 0; i < 93; i++) r += (r >> 1) + 63;
    if (r > 365784) r = r % 1890;
    return r;
}

long func_21(long a, long b) {
    long r = a + b * 25;
    for (int i = 0; i < 67; i++) r += (r >> 2) + 433;
    for (int i = 0; i < 33; i++) r += (r >> 3) + 474;
    for (int i = 0; i < 41; i++) r += (r >> 1) + 454;
    if (r > 907546) r = r % 9116;
    return r;
}

long func_22(long a, long b) {
    long r = a + b * 84;
    for (int i = 0; i < 11; i++) r += (r >> 1) + 949;
    for (int i = 0; i < 40; i++) r += (r >> 2) + 417;
    for (int i = 0; i < 72; i++) r += (r >> 4) + 219;
    if (r > 956279) r = r % 1060;
    return r;
}

long func_23(long a, long b) {
    long r = a + b * 1;
    for (int i = 0; i < 43; i++) r += (r >> 4) + 293;
    for (int i = 0; i < 64; i++) r += (r >> 5) + 678;
    if (r > 172316) r = r % 3211;
    return r;
}

long func_24(long a, long b) {
    long r = a + b * 8;
    for (int i = 0; i < 79; i++) r += (r >> 1) + 766;
    for (int i = 0; i < 50; i++) r += (r >> 1) + 52;
    for (int i = 0; i < 84; i++) r += (r >> 4) + 515;
    if (r > 566926) r = r % 2679;
    return r;
}

long func_25(long a, long b) {
    long r = a + b * 66;
    for (int i = 0; i < 33; i++) r += (r >> 1) + 610;
    long arr[35];
    for (int j = 0; j < 35; j++) arr[j] = r + j;
    for (int j = 0; j < 35; j++) r += arr[j];
    return r;
}

long func_26(long a, long b) {
    long r = a + b * 16;
    for (int i = 0; i < 41; i++) r += (r >> 5) + 609;
    for (int i = 0; i < 15; i++) r += (r >> 5) + 84;
    for (int i = 0; i < 63; i++) r += (r >> 5) + 579;
    if (r > 990110) r = r % 4372;
    return r;
}

long func_27(long a, long b) {
    long r = a + b * 92;
    for (int i = 0; i < 40; i++) r += (r >> 3) + 406;
    for (int i = 0; i < 26; i++) r += (r >> 3) + 469;
    if (r > 798387) r = r % 1288;
    return r;
}

long func_28(long a, long b) {
    long r = a + b * 80;
    for (int i = 0; i < 22; i++) r += (r >> 1) + 551;
    for (int i = 0; i < 37; i++) r += (r >> 5) + 272;
    for (int i = 0; i < 26; i++) r += (r >> 3) + 903;
    return r;
}

long func_29(long a, long b) {
    long r = a + b * 37;
    for (int i = 0; i < 66; i++) r += (r >> 5) + 721;
    if (r > 856305) r = r % 8766;
    return r;
}

long func_30(long a, long b) {
    long r = a + b * 71;
    for (int i = 0; i < 94; i++) r += (r >> 1) + 962;
    for (int i = 0; i < 27; i++) r += (r >> 3) + 119;
    if (r > 788480) r = r % 9164;
    return r;
}

long func_31(long a, long b) {
    long r = a + b * 37;
    for (int i = 0; i < 36; i++) r += (r >> 3) + 209;
    for (int i = 0; i < 97; i++) r += (r >> 3) + 518;
    for (int i = 0; i < 72; i++) r += (r >> 3) + 928;
    if (r > 63266) r = r % 1612;
    long arr[27];
    for (int j = 0; j < 27; j++) arr[j] = r + j;
    for (int j = 0; j < 27; j++) r += arr[j];
    return r;
}

long func_32(long a, long b) {
    long r = a + b * 6;
    for (int i = 0; i < 52; i++) r += (r >> 2) + 653;
    if (r > 179430) r = r % 7339;
    long arr[37];
    for (int j = 0; j < 37; j++) arr[j] = r + j;
    for (int j = 0; j < 37; j++) r += arr[j];
    return r;
}

long func_33(long a, long b) {
    long r = a + b * 72;
    for (int i = 0; i < 24; i++) r += (r >> 1) + 968;
    if (r > 957837) r = r % 2542;
    long arr[33];
    for (int j = 0; j < 33; j++) arr[j] = r + j;
    for (int j = 0; j < 33; j++) r += arr[j];
    return r;
}

long func_34(long a, long b) {
    long r = a + b * 75;
    for (int i = 0; i < 28; i++) r += (r >> 4) + 131;
    for (int i = 0; i < 15; i++) r += (r >> 3) + 374;
    for (int i = 0; i < 15; i++) r += (r >> 3) + 216;
    if (r > 709330) r = r % 1784;
    return r;
}

long func_35(long a, long b) {
    long r = a + b * 72;
    for (int i = 0; i < 89; i++) r += (r >> 2) + 948;
    for (int i = 0; i < 40; i++) r += (r >> 2) + 820;
    if (r > 934231) r = r % 6855;
    return r;
}

long func_36(long a, long b) {
    long r = a + b * 95;
    for (int i = 0; i < 62; i++) r += (r >> 2) + 274;
    for (int i = 0; i < 30; i++) r += (r >> 1) + 392;
    if (r > 910300) r = r % 7811;
    return r;
}

long func_37(long a, long b) {
    long r = a + b * 59;
    for (int i = 0; i < 49; i++) r += (r >> 2) + 229;
    for (int i = 0; i < 13; i++) r += (r >> 2) + 409;
    if (r > 916339) r = r % 1237;
    long arr[27];
    for (int j = 0; j < 27; j++) arr[j] = r + j;
    for (int j = 0; j < 27; j++) r += arr[j];
    return r;
}

long func_38(long a, long b) {
    long r = a + b * 45;
    for (int i = 0; i < 75; i++) r += (r >> 4) + 696;
    for (int i = 0; i < 78; i++) r += (r >> 3) + 962;
    for (int i = 0; i < 13; i++) r += (r >> 1) + 899;
    if (r > 197241) r = r % 9612;
    long arr[26];
    for (int j = 0; j < 26; j++) arr[j] = r + j;
    for (int j = 0; j < 26; j++) r += arr[j];
    return r;
}

long func_39(long a, long b) {
    long r = a + b * 5;
    for (int i = 0; i < 86; i++) r += (r >> 4) + 354;
    if (r > 338914) r = r % 7249;
    long arr[42];
    for (int j = 0; j < 42; j++) arr[j] = r + j;
    for (int j = 0; j < 42; j++) r += arr[j];
    return r;
}

long func_40(long a, long b) {
    long r = a + b * 15;
    for (int i = 0; i < 83; i++) r += (r >> 2) + 261;
    for (int i = 0; i < 15; i++) r += (r >> 4) + 2;
    if (r > 855687) r = r % 8921;
    long arr[22];
    for (int j = 0; j < 22; j++) arr[j] = r + j;
    for (int j = 0; j < 22; j++) r += arr[j];
    return r;
}

long func_41(long a, long b) {
    long r = a + b * 47;
    for (int i = 0; i < 18; i++) r += (r >> 3) + 639;
    for (int i = 0; i < 50; i++) r += (r >> 1) + 738;
    if (r > 541756) r = r % 5167;
    long arr[30];
    for (int j = 0; j < 30; j++) arr[j] = r + j;
    for (int j = 0; j < 30; j++) r += arr[j];
    return r;
}

long func_42(long a, long b) {
    long r = a + b * 52;
    for (int i = 0; i < 47; i++) r += (r >> 5) + 131;
    for (int i = 0; i < 34; i++) r += (r >> 4) + 681;
    for (int i = 0; i < 58; i++) r += (r >> 2) + 631;
    if (r > 435800) r = r % 9077;
    long arr[29];
    for (int j = 0; j < 29; j++) arr[j] = r + j;
    for (int j = 0; j < 29; j++) r += arr[j];
    return r;
}

long func_43(long a, long b) {
    long r = a + b * 37;
    for (int i = 0; i < 65; i++) r += (r >> 5) + 622;
    if (r > 497575) r = r % 7338;
    return r;
}

long func_44(long a, long b) {
    long r = a + b * 28;
    for (int i = 0; i < 70; i++) r += (r >> 2) + 675;
    for (int i = 0; i < 20; i++) r += (r >> 3) + 528;
    for (int i = 0; i < 94; i++) r += (r >> 5) + 344;
    long arr[25];
    for (int j = 0; j < 25; j++) arr[j] = r + j;
    for (int j = 0; j < 25; j++) r += arr[j];
    return r;
}

long func_45(long a, long b) {
    long r = a + b * 87;
    for (int i = 0; i < 38; i++) r += (r >> 2) + 151;
    for (int i = 0; i < 13; i++) r += (r >> 1) + 251;
    if (r > 650967) r = r % 1293;
    return r;
}

long func_46(long a, long b) {
    long r = a + b * 81;
    for (int i = 0; i < 34; i++) r += (r >> 4) + 507;
    for (int i = 0; i < 61; i++) r += (r >> 2) + 152;
    for (int i = 0; i < 93; i++) r += (r >> 1) + 915;
    if (r > 817451) r = r % 1846;
    long arr[24];
    for (int j = 0; j < 24; j++) arr[j] = r + j;
    for (int j = 0; j < 24; j++) r += arr[j];
    return r;
}

long func_47(long a, long b) {
    long r = a + b * 23;
    for (int i = 0; i < 76; i++) r += (r >> 4) + 52;
    for (int i = 0; i < 81; i++) r += (r >> 2) + 940;
    for (int i = 0; i < 25; i++) r += (r >> 4) + 137;
    if (r > 710005) r = r % 8802;
    long arr[48];
    for (int j = 0; j < 48; j++) arr[j] = r + j;
    for (int j = 0; j < 48; j++) r += arr[j];
    return r;
}

long func_48(long a, long b) {
    long r = a + b * 41;
    for (int i = 0; i < 88; i++) r += (r >> 5) + 437;
    for (int i = 0; i < 80; i++) r += (r >> 4) + 919;
    long arr[38];
    for (int j = 0; j < 38; j++) arr[j] = r + j;
    for (int j = 0; j < 38; j++) r += arr[j];
    return r;
}

long func_49(long a, long b) {
    long r = a + b * 34;
    for (int i = 0; i < 91; i++) r += (r >> 3) + 785;
    if (r > 518136) r = r % 4019;
    return r;
}

long func_50(long a, long b) {
    long r = a + b * 10;
    for (int i = 0; i < 46; i++) r += (r >> 2) + 279;
    for (int i = 0; i < 52; i++) r += (r >> 3) + 915;
    for (int i = 0; i < 79; i++) r += (r >> 1) + 142;
    return r;
}

long func_51(long a, long b) {
    long r = a + b * 20;
    for (int i = 0; i < 37; i++) r += (r >> 1) + 425;
    for (int i = 0; i < 62; i++) r += (r >> 3) + 556;
    for (int i = 0; i < 69; i++) r += (r >> 4) + 64;
    return r;
}

long func_52(long a, long b) {
    long r = a + b * 99;
    for (int i = 0; i < 99; i++) r += (r >> 1) + 878;
    for (int i = 0; i < 83; i++) r += (r >> 4) + 489;
    for (int i = 0; i < 10; i++) r += (r >> 3) + 306;
    if (r > 904905) r = r % 6965;
    long arr[44];
    for (int j = 0; j < 44; j++) arr[j] = r + j;
    for (int j = 0; j < 44; j++) r += arr[j];
    return r;
}

long func_53(long a, long b) {
    long r = a + b * 78;
    for (int i = 0; i < 72; i++) r += (r >> 2) + 280;
    if (r > 40434) r = r % 6471;
    return r;
}

long func_54(long a, long b) {
    long r = a + b * 87;
    for (int i = 0; i < 31; i++) r += (r >> 4) + 942;
    for (int i = 0; i < 26; i++) r += (r >> 5) + 547;
    return r;
}

long func_55(long a, long b) {
    long r = a + b * 73;
    for (int i = 0; i < 13; i++) r += (r >> 1) + 659;
    for (int i = 0; i < 64; i++) r += (r >> 2) + 888;
    for (int i = 0; i < 69; i++) r += (r >> 2) + 52;
    return r;
}

long func_56(long a, long b) {
    long r = a + b * 59;
    for (int i = 0; i < 53; i++) r += (r >> 4) + 285;
    for (int i = 0; i < 63; i++) r += (r >> 3) + 855;
    return r;
}

long func_57(long a, long b) {
    long r = a + b * 70;
    for (int i = 0; i < 54; i++) r += (r >> 2) + 666;
    long arr[12];
    for (int j = 0; j < 12; j++) arr[j] = r + j;
    for (int j = 0; j < 12; j++) r += arr[j];
    return r;
}

long func_58(long a, long b) {
    long r = a + b * 97;
    for (int i = 0; i < 41; i++) r += (r >> 2) + 860;
    return r;
}

long func_59(long a, long b) {
    long r = a + b * 17;
    for (int i = 0; i < 95; i++) r += (r >> 1) + 578;
    for (int i = 0; i < 37; i++) r += (r >> 4) + 717;
    return r;
}

long func_60(long a, long b) {
    long r = a + b * 78;
    for (int i = 0; i < 24; i++) r += (r >> 2) + 988;
    for (int i = 0; i < 49; i++) r += (r >> 1) + 593;
    for (int i = 0; i < 13; i++) r += (r >> 3) + 590;
    if (r > 403537) r = r % 6598;
    long arr[22];
    for (int j = 0; j < 22; j++) arr[j] = r + j;
    for (int j = 0; j < 22; j++) r += arr[j];
    return r;
}

long func_61(long a, long b) {
    long r = a + b * 10;
    for (int i = 0; i < 98; i++) r += (r >> 2) + 105;
    for (int i = 0; i < 99; i++) r += (r >> 3) + 871;
    for (int i = 0; i < 97; i++) r += (r >> 5) + 825;
    long arr[12];
    for (int j = 0; j < 12; j++) arr[j] = r + j;
    for (int j = 0; j < 12; j++) r += arr[j];
    return r;
}

long func_62(long a, long b) {
    long r = a + b * 45;
    for (int i = 0; i < 64; i++) r += (r >> 3) + 71;
    for (int i = 0; i < 74; i++) r += (r >> 3) + 13;
    for (int i = 0; i < 63; i++) r += (r >> 4) + 109;
    if (r > 389781) r = r % 7632;
    long arr[37];
    for (int j = 0; j < 37; j++) arr[j] = r + j;
    for (int j = 0; j < 37; j++) r += arr[j];
    return r;
}

long func_63(long a, long b) {
    long r = a + b * 23;
    for (int i = 0; i < 76; i++) r += (r >> 3) + 631;
    for (int i = 0; i < 78; i++) r += (r >> 4) + 477;
    for (int i = 0; i < 65; i++) r += (r >> 5) + 275;
    if (r > 267420) r = r % 1519;
    return r;
}

long func_64(long a, long b) {
    long r = a + b * 58;
    for (int i = 0; i < 69; i++) r += (r >> 5) + 625;
    if (r > 362737) r = r % 570;
    return r;
}

long func_65(long a, long b) {
    long r = a + b * 42;
    for (int i = 0; i < 72; i++) r += (r >> 2) + 364;
    if (r > 366871) r = r % 4681;
    long arr[27];
    for (int j = 0; j < 27; j++) arr[j] = r + j;
    for (int j = 0; j < 27; j++) r += arr[j];
    return r;
}

long func_66(long a, long b) {
    long r = a + b * 72;
    for (int i = 0; i < 76; i++) r += (r >> 2) + 88;
    return r;
}

long func_67(long a, long b) {
    long r = a + b * 72;
    for (int i = 0; i < 98; i++) r += (r >> 4) + 662;
    if (r > 479945) r = r % 382;
    return r;
}

long func_68(long a, long b) {
    long r = a + b * 29;
    for (int i = 0; i < 98; i++) r += (r >> 2) + 314;
    for (int i = 0; i < 94; i++) r += (r >> 5) + 378;
    if (r > 566711) r = r % 5732;
    return r;
}

long func_69(long a, long b) {
    long r = a + b * 96;
    for (int i = 0; i < 52; i++) r += (r >> 3) + 720;
    for (int i = 0; i < 68; i++) r += (r >> 3) + 314;
    for (int i = 0; i < 42; i++) r += (r >> 2) + 124;
    if (r > 340876) r = r % 2058;
    long arr[21];
    for (int j = 0; j < 21; j++) arr[j] = r + j;
    for (int j = 0; j < 21; j++) r += arr[j];
    return r;
}

long func_70(long a, long b) {
    long r = a + b * 25;
    for (int i = 0; i < 71; i++) r += (r >> 3) + 742;
    if (r > 807135) r = r % 8695;
    long arr[16];
    for (int j = 0; j < 16; j++) arr[j] = r + j;
    for (int j = 0; j < 16; j++) r += arr[j];
    return r;
}

long func_71(long a, long b) {
    long r = a + b * 25;
    for (int i = 0; i < 39; i++) r += (r >> 3) + 184;
    for (int i = 0; i < 48; i++) r += (r >> 1) + 726;
    if (r > 297636) r = r % 845;
    long arr[45];
    for (int j = 0; j < 45; j++) arr[j] = r + j;
    for (int j = 0; j < 45; j++) r += arr[j];
    return r;
}

long func_72(long a, long b) {
    long r = a + b * 38;
    for (int i = 0; i < 26; i++) r += (r >> 4) + 106;
    for (int i = 0; i < 11; i++) r += (r >> 5) + 292;
    for (int i = 0; i < 70; i++) r += (r >> 4) + 452;
    if (r > 63872) r = r % 4236;
    long arr[40];
    for (int j = 0; j < 40; j++) arr[j] = r + j;
    for (int j = 0; j < 40; j++) r += arr[j];
    return r;
}

long func_73(long a, long b) {
    long r = a + b * 15;
    for (int i = 0; i < 61; i++) r += (r >> 4) + 76;
    if (r > 729796) r = r % 978;
    return r;
}

long func_74(long a, long b) {
    long r = a + b * 73;
    for (int i = 0; i < 20; i++) r += (r >> 2) + 122;
    for (int i = 0; i < 81; i++) r += (r >> 4) + 621;
    if (r > 658458) r = r % 3797;
    long arr[34];
    for (int j = 0; j < 34; j++) arr[j] = r + j;
    for (int j = 0; j < 34; j++) r += arr[j];
    return r;
}

long func_75(long a, long b) {
    long r = a + b * 58;
    for (int i = 0; i < 48; i++) r += (r >> 5) + 440;
    for (int i = 0; i < 49; i++) r += (r >> 5) + 636;
    long arr[16];
    for (int j = 0; j < 16; j++) arr[j] = r + j;
    for (int j = 0; j < 16; j++) r += arr[j];
    return r;
}

long func_76(long a, long b) {
    long r = a + b * 98;
    for (int i = 0; i < 90; i++) r += (r >> 2) + 271;
    if (r > 174686) r = r % 4029;
    return r;
}

long func_77(long a, long b) {
    long r = a + b * 10;
    for (int i = 0; i < 10; i++) r += (r >> 4) + 462;
    if (r > 502738) r = r % 4871;
    return r;
}

long func_78(long a, long b) {
    long r = a + b * 37;
    for (int i = 0; i < 46; i++) r += (r >> 4) + 73;
    for (int i = 0; i < 97; i++) r += (r >> 2) + 947;
    for (int i = 0; i < 43; i++) r += (r >> 5) + 678;
    if (r > 217428) r = r % 7065;
    return r;
}

long func_79(long a, long b) {
    long r = a + b * 29;
    for (int i = 0; i < 29; i++) r += (r >> 3) + 847;
    for (int i = 0; i < 28; i++) r += (r >> 1) + 62;
    for (int i = 0; i < 31; i++) r += (r >> 3) + 610;
    if (r > 606856) r = r % 4828;
    return r;
}

long func_80(long a, long b) {
    long r = a + b * 60;
    for (int i = 0; i < 48; i++) r += (r >> 4) + 966;
    for (int i = 0; i < 44; i++) r += (r >> 5) + 553;
    for (int i = 0; i < 73; i++) r += (r >> 4) + 83;
    if (r > 942627) r = r % 7178;
    long arr[48];
    for (int j = 0; j < 48; j++) arr[j] = r + j;
    for (int j = 0; j < 48; j++) r += arr[j];
    return r;
}

long func_81(long a, long b) {
    long r = a + b * 33;
    for (int i = 0; i < 21; i++) r += (r >> 2) + 985;
    if (r > 912317) r = r % 9524;
    long arr[11];
    for (int j = 0; j < 11; j++) arr[j] = r + j;
    for (int j = 0; j < 11; j++) r += arr[j];
    return r;
}

long func_82(long a, long b) {
    long r = a + b * 98;
    for (int i = 0; i < 44; i++) r += (r >> 5) + 42;
    for (int i = 0; i < 32; i++) r += (r >> 4) + 532;
    for (int i = 0; i < 93; i++) r += (r >> 4) + 939;
    long arr[37];
    for (int j = 0; j < 37; j++) arr[j] = r + j;
    for (int j = 0; j < 37; j++) r += arr[j];
    return r;
}

long func_83(long a, long b) {
    long r = a + b * 82;
    for (int i = 0; i < 21; i++) r += (r >> 4) + 357;
    for (int i = 0; i < 62; i++) r += (r >> 3) + 329;
    if (r > 909398) r = r % 2734;
    return r;
}

long func_84(long a, long b) {
    long r = a + b * 89;
    for (int i = 0; i < 46; i++) r += (r >> 4) + 834;
    for (int i = 0; i < 80; i++) r += (r >> 1) + 466;
    return r;
}

long func_85(long a, long b) {
    long r = a + b * 15;
    for (int i = 0; i < 75; i++) r += (r >> 1) + 674;
    for (int i = 0; i < 79; i++) r += (r >> 4) + 424;
    long arr[49];
    for (int j = 0; j < 49; j++) arr[j] = r + j;
    for (int j = 0; j < 49; j++) r += arr[j];
    return r;
}

long func_86(long a, long b) {
    long r = a + b * 97;
    for (int i = 0; i < 90; i++) r += (r >> 4) + 779;
    for (int i = 0; i < 16; i++) r += (r >> 2) + 274;
    if (r > 982735) r = r % 4819;
    return r;
}

long func_87(long a, long b) {
    long r = a + b * 90;
    for (int i = 0; i < 25; i++) r += (r >> 1) + 997;
    for (int i = 0; i < 90; i++) r += (r >> 5) + 819;
    return r;
}

long func_88(long a, long b) {
    long r = a + b * 71;
    for (int i = 0; i < 80; i++) r += (r >> 4) + 96;
    long arr[17];
    for (int j = 0; j < 17; j++) arr[j] = r + j;
    for (int j = 0; j < 17; j++) r += arr[j];
    return r;
}

long func_89(long a, long b) {
    long r = a + b * 60;
    for (int i = 0; i < 92; i++) r += (r >> 2) + 511;
    if (r > 316039) r = r % 8437;
    long arr[36];
    for (int j = 0; j < 36; j++) arr[j] = r + j;
    for (int j = 0; j < 36; j++) r += arr[j];
    return r;
}

long func_90(long a, long b) {
    long r = a + b * 62;
    for (int i = 0; i < 41; i++) r += (r >> 4) + 565;
    for (int i = 0; i < 28; i++) r += (r >> 4) + 196;
    if (r > 542929) r = r % 2336;
    long arr[27];
    for (int j = 0; j < 27; j++) arr[j] = r + j;
    for (int j = 0; j < 27; j++) r += arr[j];
    return r;
}

long func_91(long a, long b) {
    long r = a + b * 99;
    for (int i = 0; i < 53; i++) r += (r >> 5) + 274;
    for (int i = 0; i < 10; i++) r += (r >> 3) + 744;
    long arr[41];
    for (int j = 0; j < 41; j++) arr[j] = r + j;
    for (int j = 0; j < 41; j++) r += arr[j];
    return r;
}

long func_92(long a, long b) {
    long r = a + b * 20;
    for (int i = 0; i < 78; i++) r += (r >> 4) + 354;
    for (int i = 0; i < 52; i++) r += (r >> 5) + 782;
    if (r > 487463) r = r % 5372;
    long arr[25];
    for (int j = 0; j < 25; j++) arr[j] = r + j;
    for (int j = 0; j < 25; j++) r += arr[j];
    return r;
}

long func_93(long a, long b) {
    long r = a + b * 74;
    for (int i = 0; i < 39; i++) r += (r >> 4) + 45;
    for (int i = 0; i < 50; i++) r += (r >> 4) + 723;
    if (r > 409749) r = r % 6425;
    long arr[19];
    for (int j = 0; j < 19; j++) arr[j] = r + j;
    for (int j = 0; j < 19; j++) r += arr[j];
    return r;
}

long func_94(long a, long b) {
    long r = a + b * 64;
    for (int i = 0; i < 26; i++) r += (r >> 5) + 989;
    if (r > 921946) r = r % 1744;
    long arr[38];
    for (int j = 0; j < 38; j++) arr[j] = r + j;
    for (int j = 0; j < 38; j++) r += arr[j];
    return r;
}

long func_95(long a, long b) {
    long r = a + b * 13;
    for (int i = 0; i < 68; i++) r += (r >> 1) + 740;
    for (int i = 0; i < 28; i++) r += (r >> 4) + 892;
    for (int i = 0; i < 93; i++) r += (r >> 2) + 77;
    if (r > 287896) r = r % 5646;
    long arr[35];
    for (int j = 0; j < 35; j++) arr[j] = r + j;
    for (int j = 0; j < 35; j++) r += arr[j];
    return r;
}

long func_96(long a, long b) {
    long r = a + b * 84;
    for (int i = 0; i < 52; i++) r += (r >> 5) + 390;
    if (r > 667246) r = r % 8094;
    long arr[12];
    for (int j = 0; j < 12; j++) arr[j] = r + j;
    for (int j = 0; j < 12; j++) r += arr[j];
    return r;
}

long func_97(long a, long b) {
    long r = a + b * 80;
    for (int i = 0; i < 40; i++) r += (r >> 3) + 233;
    if (r > 465052) r = r % 1712;
    long arr[16];
    for (int j = 0; j < 16; j++) arr[j] = r + j;
    for (int j = 0; j < 16; j++) r += arr[j];
    return r;
}

long func_98(long a, long b) {
    long r = a + b * 57;
    for (int i = 0; i < 98; i++) r += (r >> 3) + 926;
    return r;
}

long func_99(long a, long b) {
    long r = a + b * 8;
    for (int i = 0; i < 55; i++) r += (r >> 3) + 442;
    for (int i = 0; i < 28; i++) r += (r >> 2) + 544;
    if (r > 724919) r = r % 3050;
    return r;
}

long func_100(long a, long b) {
    long r = a + b * 11;
    for (int i = 0; i < 58; i++) r += (r >> 5) + 700;
    for (int i = 0; i < 40; i++) r += (r >> 4) + 935;
    for (int i = 0; i < 84; i++) r += (r >> 2) + 238;
    if (r > 276314) r = r % 7629;
    return r;
}

long func_101(long a, long b) {
    long r = a + b * 2;
    for (int i = 0; i < 46; i++) r += (r >> 5) + 162;
    for (int i = 0; i < 19; i++) r += (r >> 4) + 968;
    if (r > 626113) r = r % 5001;
    long arr[37];
    for (int j = 0; j < 37; j++) arr[j] = r + j;
    for (int j = 0; j < 37; j++) r += arr[j];
    return r;
}

long func_102(long a, long b) {
    long r = a + b * 89;
    for (int i = 0; i < 68; i++) r += (r >> 3) + 204;
    for (int i = 0; i < 59; i++) r += (r >> 4) + 110;
    long arr[46];
    for (int j = 0; j < 46; j++) arr[j] = r + j;
    for (int j = 0; j < 46; j++) r += arr[j];
    return r;
}

long func_103(long a, long b) {
    long r = a + b * 38;
    for (int i = 0; i < 47; i++) r += (r >> 1) + 850;
    for (int i = 0; i < 94; i++) r += (r >> 4) + 282;
    for (int i = 0; i < 11; i++) r += (r >> 5) + 886;
    if (r > 790841) r = r % 903;
    long arr[41];
    for (int j = 0; j < 41; j++) arr[j] = r + j;
    for (int j = 0; j < 41; j++) r += arr[j];
    return r;
}

long func_104(long a, long b) {
    long r = a + b * 37;
    for (int i = 0; i < 87; i++) r += (r >> 3) + 225;
    if (r > 661051) r = r % 4206;
    long arr[18];
    for (int j = 0; j < 18; j++) arr[j] = r + j;
    for (int j = 0; j < 18; j++) r += arr[j];
    return r;
}

long func_105(long a, long b) {
    long r = a + b * 81;
    for (int i = 0; i < 90; i++) r += (r >> 1) + 317;
    if (r > 44985) r = r % 9595;
    return r;
}

long func_106(long a, long b) {
    long r = a + b * 17;
    for (int i = 0; i < 47; i++) r += (r >> 3) + 766;
    if (r > 220548) r = r % 2265;
    long arr[33];
    for (int j = 0; j < 33; j++) arr[j] = r + j;
    for (int j = 0; j < 33; j++) r += arr[j];
    return r;
}

long func_107(long a, long b) {
    long r = a + b * 68;
    for (int i = 0; i < 44; i++) r += (r >> 2) + 264;
    for (int i = 0; i < 71; i++) r += (r >> 3) + 765;
    for (int i = 0; i < 53; i++) r += (r >> 1) + 480;
    if (r > 157594) r = r % 3796;
    long arr[35];
    for (int j = 0; j < 35; j++) arr[j] = r + j;
    for (int j = 0; j < 35; j++) r += arr[j];
    return r;
}

long func_108(long a, long b) {
    long r = a + b * 72;
    for (int i = 0; i < 21; i++) r += (r >> 4) + 15;
    for (int i = 0; i < 43; i++) r += (r >> 5) + 127;
    if (r > 715511) r = r % 4395;
    long arr[50];
    for (int j = 0; j < 50; j++) arr[j] = r + j;
    for (int j = 0; j < 50; j++) r += arr[j];
    return r;
}

long func_109(long a, long b) {
    long r = a + b * 48;
    for (int i = 0; i < 96; i++) r += (r >> 2) + 483;
    long arr[45];
    for (int j = 0; j < 45; j++) arr[j] = r + j;
    for (int j = 0; j < 45; j++) r += arr[j];
    return r;
}

long func_110(long a, long b) {
    long r = a + b * 42;
    for (int i = 0; i < 38; i++) r += (r >> 1) + 651;
    for (int i = 0; i < 69; i++) r += (r >> 3) + 665;
    for (int i = 0; i < 62; i++) r += (r >> 1) + 144;
    return r;
}

long func_111(long a, long b) {
    long r = a + b * 64;
    for (int i = 0; i < 22; i++) r += (r >> 2) + 909;
    if (r > 417524) r = r % 7532;
    return r;
}

long func_112(long a, long b) {
    long r = a + b * 96;
    for (int i = 0; i < 79; i++) r += (r >> 4) + 602;
    for (int i = 0; i < 29; i++) r += (r >> 4) + 671;
    for (int i = 0; i < 22; i++) r += (r >> 4) + 631;
    if (r > 303328) r = r % 636;
    long arr[23];
    for (int j = 0; j < 23; j++) arr[j] = r + j;
    for (int j = 0; j < 23; j++) r += arr[j];
    return r;
}

long func_113(long a, long b) {
    long r = a + b * 57;
    for (int i = 0; i < 40; i++) r += (r >> 3) + 102;
    for (int i = 0; i < 97; i++) r += (r >> 3) + 558;
    if (r > 686149) r = r % 5976;
    return r;
}

long func_114(long a, long b) {
    long r = a + b * 36;
    for (int i = 0; i < 25; i++) r += (r >> 4) + 94;
    if (r > 682875) r = r % 9883;
    long arr[13];
    for (int j = 0; j < 13; j++) arr[j] = r + j;
    for (int j = 0; j < 13; j++) r += arr[j];
    return r;
}

long func_115(long a, long b) {
    long r = a + b * 43;
    for (int i = 0; i < 26; i++) r += (r >> 5) + 211;
    long arr[23];
    for (int j = 0; j < 23; j++) arr[j] = r + j;
    for (int j = 0; j < 23; j++) r += arr[j];
    return r;
}

long func_116(long a, long b) {
    long r = a + b * 76;
    for (int i = 0; i < 39; i++) r += (r >> 3) + 793;
    long arr[10];
    for (int j = 0; j < 10; j++) arr[j] = r + j;
    for (int j = 0; j < 10; j++) r += arr[j];
    return r;
}

long func_117(long a, long b) {
    long r = a + b * 36;
    for (int i = 0; i < 26; i++) r += (r >> 5) + 257;
    if (r > 125266) r = r % 522;
    return r;
}

long func_118(long a, long b) {
    long r = a + b * 46;
    for (int i = 0; i < 85; i++) r += (r >> 3) + 17;
    return r;
}

long func_119(long a, long b) {
    long r = a + b * 95;
    for (int i = 0; i < 77; i++) r += (r >> 1) + 764;
    for (int i = 0; i < 18; i++) r += (r >> 4) + 460;
    if (r > 548169) r = r % 9826;
    return r;
}

long func_120(long a, long b) {
    long r = a + b * 65;
    for (int i = 0; i < 88; i++) r += (r >> 1) + 745;
    if (r > 919095) r = r % 8643;
    return r;
}

long func_121(long a, long b) {
    long r = a + b * 83;
    for (int i = 0; i < 17; i++) r += (r >> 4) + 868;
    if (r > 729425) r = r % 1868;
    return r;
}

long func_122(long a, long b) {
    long r = a + b * 57;
    for (int i = 0; i < 20; i++) r += (r >> 3) + 623;
    return r;
}

long func_123(long a, long b) {
    long r = a + b * 80;
    for (int i = 0; i < 84; i++) r += (r >> 5) + 730;
    for (int i = 0; i < 51; i++) r += (r >> 4) + 612;
    for (int i = 0; i < 77; i++) r += (r >> 3) + 465;
    if (r > 461096) r = r % 1724;
    long arr[17];
    for (int j = 0; j < 17; j++) arr[j] = r + j;
    for (int j = 0; j < 17; j++) r += arr[j];
    return r;
}

long func_124(long a, long b) {
    long r = a + b * 84;
    for (int i = 0; i < 80; i++) r += (r >> 2) + 441;
    for (int i = 0; i < 67; i++) r += (r >> 2) + 424;
    for (int i = 0; i < 53; i++) r += (r >> 4) + 409;
    if (r > 109704) r = r % 5220;
    return r;
}

long func_125(long a, long b) {
    long r = a + b * 86;
    for (int i = 0; i < 57; i++) r += (r >> 2) + 704;
    for (int i = 0; i < 70; i++) r += (r >> 1) + 94;
    if (r > 107758) r = r % 7175;
    return r;
}

long func_126(long a, long b) {
    long r = a + b * 95;
    for (int i = 0; i < 26; i++) r += (r >> 5) + 62;
    for (int i = 0; i < 85; i++) r += (r >> 5) + 576;
    if (r > 138168) r = r % 6830;
    return r;
}

long func_127(long a, long b) {
    long r = a + b * 86;
    for (int i = 0; i < 16; i++) r += (r >> 3) + 615;
    for (int i = 0; i < 49; i++) r += (r >> 3) + 107;
    if (r > 233072) r = r % 2635;
    long arr[24];
    for (int j = 0; j < 24; j++) arr[j] = r + j;
    for (int j = 0; j < 24; j++) r += arr[j];
    return r;
}

long func_128(long a, long b) {
    long r = a + b * 14;
    for (int i = 0; i < 81; i++) r += (r >> 3) + 118;
    for (int i = 0; i < 45; i++) r += (r >> 5) + 232;
    if (r > 896209) r = r % 9290;
    long arr[49];
    for (int j = 0; j < 49; j++) arr[j] = r + j;
    for (int j = 0; j < 49; j++) r += arr[j];
    return r;
}

long func_129(long a, long b) {
    long r = a + b * 79;
    for (int i = 0; i < 92; i++) r += (r >> 5) + 27;
    for (int i = 0; i < 87; i++) r += (r >> 3) + 30;
    for (int i = 0; i < 33; i++) r += (r >> 3) + 720;
    if (r > 976302) r = r % 5667;
    return r;
}

long func_130(long a, long b) {
    long r = a + b * 24;
    for (int i = 0; i < 82; i++) r += (r >> 4) + 72;
    long arr[11];
    for (int j = 0; j < 11; j++) arr[j] = r + j;
    for (int j = 0; j < 11; j++) r += arr[j];
    return r;
}

long func_131(long a, long b) {
    long r = a + b * 12;
    for (int i = 0; i < 77; i++) r += (r >> 2) + 386;
    for (int i = 0; i < 63; i++) r += (r >> 4) + 350;
    for (int i = 0; i < 30; i++) r += (r >> 3) + 320;
    if (r > 824571) r = r % 9399;
    long arr[13];
    for (int j = 0; j < 13; j++) arr[j] = r + j;
    for (int j = 0; j < 13; j++) r += arr[j];
    return r;
}

long func_132(long a, long b) {
    long r = a + b * 20;
    for (int i = 0; i < 89; i++) r += (r >> 1) + 691;
    return r;
}

long func_133(long a, long b) {
    long r = a + b * 55;
    for (int i = 0; i < 87; i++) r += (r >> 4) + 425;
    for (int i = 0; i < 44; i++) r += (r >> 2) + 774;
    if (r > 371939) r = r % 7143;
    return r;
}

long func_134(long a, long b) {
    long r = a + b * 87;
    for (int i = 0; i < 85; i++) r += (r >> 4) + 540;
    for (int i = 0; i < 95; i++) r += (r >> 3) + 47;
    for (int i = 0; i < 38; i++) r += (r >> 4) + 614;
    return r;
}

long func_135(long a, long b) {
    long r = a + b * 28;
    for (int i = 0; i < 42; i++) r += (r >> 3) + 336;
    return r;
}

long func_136(long a, long b) {
    long r = a + b * 56;
    for (int i = 0; i < 26; i++) r += (r >> 4) + 546;
    if (r > 534563) r = r % 9254;
    long arr[32];
    for (int j = 0; j < 32; j++) arr[j] = r + j;
    for (int j = 0; j < 32; j++) r += arr[j];
    return r;
}

long func_137(long a, long b) {
    long r = a + b * 10;
    for (int i = 0; i < 15; i++) r += (r >> 4) + 20;
    for (int i = 0; i < 68; i++) r += (r >> 1) + 883;
    if (r > 460137) r = r % 9494;
    return r;
}

long func_138(long a, long b) {
    long r = a + b * 82;
    for (int i = 0; i < 47; i++) r += (r >> 1) + 415;
    for (int i = 0; i < 12; i++) r += (r >> 3) + 176;
    if (r > 658151) r = r % 7638;
    long arr[33];
    for (int j = 0; j < 33; j++) arr[j] = r + j;
    for (int j = 0; j < 33; j++) r += arr[j];
    return r;
}

long func_139(long a, long b) {
    long r = a + b * 12;
    for (int i = 0; i < 23; i++) r += (r >> 2) + 447;
    for (int i = 0; i < 85; i++) r += (r >> 4) + 537;
    long arr[31];
    for (int j = 0; j < 31; j++) arr[j] = r + j;
    for (int j = 0; j < 31; j++) r += arr[j];
    return r;
}

long func_140(long a, long b) {
    long r = a + b * 29;
    for (int i = 0; i < 31; i++) r += (r >> 1) + 523;
    for (int i = 0; i < 91; i++) r += (r >> 1) + 544;
    if (r > 959928) r = r % 5824;
    return r;
}

long func_141(long a, long b) {
    long r = a + b * 83;
    for (int i = 0; i < 40; i++) r += (r >> 1) + 150;
    return r;
}

long func_142(long a, long b) {
    long r = a + b * 20;
    for (int i = 0; i < 19; i++) r += (r >> 2) + 975;
    for (int i = 0; i < 90; i++) r += (r >> 4) + 476;
    for (int i = 0; i < 82; i++) r += (r >> 5) + 460;
    if (r > 934894) r = r % 9348;
    long arr[49];
    for (int j = 0; j < 49; j++) arr[j] = r + j;
    for (int j = 0; j < 49; j++) r += arr[j];
    return r;
}

long func_143(long a, long b) {
    long r = a + b * 42;
    for (int i = 0; i < 50; i++) r += (r >> 2) + 451;
    for (int i = 0; i < 18; i++) r += (r >> 4) + 453;
    for (int i = 0; i < 90; i++) r += (r >> 3) + 816;
    return r;
}

long func_144(long a, long b) {
    long r = a + b * 65;
    for (int i = 0; i < 49; i++) r += (r >> 4) + 463;
    return r;
}

long func_145(long a, long b) {
    long r = a + b * 37;
    for (int i = 0; i < 92; i++) r += (r >> 1) + 630;
    if (r > 413159) r = r % 7681;
    long arr[12];
    for (int j = 0; j < 12; j++) arr[j] = r + j;
    for (int j = 0; j < 12; j++) r += arr[j];
    return r;
}

long func_146(long a, long b) {
    long r = a + b * 58;
    for (int i = 0; i < 93; i++) r += (r >> 2) + 330;
    for (int i = 0; i < 87; i++) r += (r >> 4) + 514;
    for (int i = 0; i < 29; i++) r += (r >> 1) + 462;
    long arr[31];
    for (int j = 0; j < 31; j++) arr[j] = r + j;
    for (int j = 0; j < 31; j++) r += arr[j];
    return r;
}

long func_147(long a, long b) {
    long r = a + b * 92;
    for (int i = 0; i < 74; i++) r += (r >> 2) + 41;
    return r;
}

long func_148(long a, long b) {
    long r = a + b * 57;
    for (int i = 0; i < 76; i++) r += (r >> 5) + 163;
    for (int i = 0; i < 56; i++) r += (r >> 3) + 940;
    for (int i = 0; i < 46; i++) r += (r >> 4) + 419;
    if (r > 721875) r = r % 9895;
    return r;
}

long func_149(long a, long b) {
    long r = a + b * 81;
    for (int i = 0; i < 52; i++) r += (r >> 1) + 338;
    for (int i = 0; i < 22; i++) r += (r >> 5) + 695;
    for (int i = 0; i < 59; i++) r += (r >> 3) + 259;
    if (r > 698457) r = r % 9974;
    long arr[31];
    for (int j = 0; j < 31; j++) arr[j] = r + j;
    for (int j = 0; j < 31; j++) r += arr[j];
    return r;
}

long func_150(long a, long b) {
    long r = a + b * 11;
    for (int i = 0; i < 94; i++) r += (r >> 2) + 939;
    for (int i = 0; i < 54; i++) r += (r >> 3) + 991;
    for (int i = 0; i < 93; i++) r += (r >> 4) + 133;
    if (r > 993566) r = r % 1488;
    return r;
}

long func_151(long a, long b) {
    long r = a + b * 49;
    for (int i = 0; i < 52; i++) r += (r >> 2) + 687;
    for (int i = 0; i < 99; i++) r += (r >> 5) + 96;
    for (int i = 0; i < 92; i++) r += (r >> 4) + 521;
    if (r > 390211) r = r % 5160;
    return r;
}

long func_152(long a, long b) {
    long r = a + b * 28;
    for (int i = 0; i < 72; i++) r += (r >> 2) + 232;
    for (int i = 0; i < 27; i++) r += (r >> 2) + 80;
    long arr[42];
    for (int j = 0; j < 42; j++) arr[j] = r + j;
    for (int j = 0; j < 42; j++) r += arr[j];
    return r;
}

long func_153(long a, long b) {
    long r = a + b * 99;
    for (int i = 0; i < 77; i++) r += (r >> 1) + 678;
    for (int i = 0; i < 53; i++) r += (r >> 5) + 135;
    for (int i = 0; i < 86; i++) r += (r >> 4) + 158;
    long arr[49];
    for (int j = 0; j < 49; j++) arr[j] = r + j;
    for (int j = 0; j < 49; j++) r += arr[j];
    return r;
}

long func_154(long a, long b) {
    long r = a + b * 22;
    for (int i = 0; i < 66; i++) r += (r >> 1) + 421;
    for (int i = 0; i < 56; i++) r += (r >> 2) + 993;
    for (int i = 0; i < 66; i++) r += (r >> 5) + 292;
    if (r > 831874) r = r % 7455;
    return r;
}

long func_155(long a, long b) {
    long r = a + b * 31;
    for (int i = 0; i < 70; i++) r += (r >> 2) + 377;
    for (int i = 0; i < 96; i++) r += (r >> 5) + 452;
    if (r > 305459) r = r % 6356;
    long arr[36];
    for (int j = 0; j < 36; j++) arr[j] = r + j;
    for (int j = 0; j < 36; j++) r += arr[j];
    return r;
}

long func_156(long a, long b) {
    long r = a + b * 21;
    for (int i = 0; i < 87; i++) r += (r >> 2) + 894;
    long arr[33];
    for (int j = 0; j < 33; j++) arr[j] = r + j;
    for (int j = 0; j < 33; j++) r += arr[j];
    return r;
}

long func_157(long a, long b) {
    long r = a + b * 71;
    for (int i = 0; i < 76; i++) r += (r >> 1) + 292;
    return r;
}

long func_158(long a, long b) {
    long r = a + b * 58;
    for (int i = 0; i < 28; i++) r += (r >> 4) + 94;
    for (int i = 0; i < 38; i++) r += (r >> 4) + 906;
    for (int i = 0; i < 54; i++) r += (r >> 1) + 425;
    long arr[25];
    for (int j = 0; j < 25; j++) arr[j] = r + j;
    for (int j = 0; j < 25; j++) r += arr[j];
    return r;
}

long func_159(long a, long b) {
    long r = a + b * 50;
    for (int i = 0; i < 57; i++) r += (r >> 2) + 29;
    if (r > 113896) r = r % 5593;
    long arr[18];
    for (int j = 0; j < 18; j++) arr[j] = r + j;
    for (int j = 0; j < 18; j++) r += arr[j];
    return r;
}

long func_160(long a, long b) {
    long r = a + b * 5;
    for (int i = 0; i < 70; i++) r += (r >> 2) + 778;
    for (int i = 0; i < 100; i++) r += (r >> 4) + 460;
    if (r > 959860) r = r % 1398;
    return r;
}

long func_161(long a, long b) {
    long r = a + b * 28;
    for (int i = 0; i < 80; i++) r += (r >> 5) + 541;
    if (r > 823875) r = r % 4820;
    return r;
}

long func_162(long a, long b) {
    long r = a + b * 16;
    for (int i = 0; i < 40; i++) r += (r >> 4) + 655;
    if (r > 489318) r = r % 1129;
    return r;
}

long func_163(long a, long b) {
    long r = a + b * 64;
    for (int i = 0; i < 78; i++) r += (r >> 1) + 648;
    for (int i = 0; i < 75; i++) r += (r >> 5) + 248;
    for (int i = 0; i < 28; i++) r += (r >> 3) + 440;
    return r;
}

long func_164(long a, long b) {
    long r = a + b * 74;
    for (int i = 0; i < 33; i++) r += (r >> 1) + 537;
    for (int i = 0; i < 56; i++) r += (r >> 1) + 977;
    if (r > 541971) r = r % 8416;
    long arr[34];
    for (int j = 0; j < 34; j++) arr[j] = r + j;
    for (int j = 0; j < 34; j++) r += arr[j];
    return r;
}

long func_165(long a, long b) {
    long r = a + b * 61;
    for (int i = 0; i < 91; i++) r += (r >> 4) + 383;
    return r;
}

long func_166(long a, long b) {
    long r = a + b * 9;
    for (int i = 0; i < 40; i++) r += (r >> 1) + 791;
    for (int i = 0; i < 84; i++) r += (r >> 3) + 137;
    long arr[21];
    for (int j = 0; j < 21; j++) arr[j] = r + j;
    for (int j = 0; j < 21; j++) r += arr[j];
    return r;
}

long func_167(long a, long b) {
    long r = a + b * 88;
    for (int i = 0; i < 99; i++) r += (r >> 4) + 647;
    for (int i = 0; i < 33; i++) r += (r >> 2) + 65;
    if (r > 999441) r = r % 7598;
    return r;
}

long func_168(long a, long b) {
    long r = a + b * 26;
    for (int i = 0; i < 35; i++) r += (r >> 1) + 324;
    if (r > 550418) r = r % 6624;
    long arr[44];
    for (int j = 0; j < 44; j++) arr[j] = r + j;
    for (int j = 0; j < 44; j++) r += arr[j];
    return r;
}

long func_169(long a, long b) {
    long r = a + b * 61;
    for (int i = 0; i < 14; i++) r += (r >> 2) + 293;
    for (int i = 0; i < 55; i++) r += (r >> 1) + 887;
    if (r > 296488) r = r % 2139;
    long arr[37];
    for (int j = 0; j < 37; j++) arr[j] = r + j;
    for (int j = 0; j < 37; j++) r += arr[j];
    return r;
}

long func_170(long a, long b) {
    long r = a + b * 52;
    for (int i = 0; i < 66; i++) r += (r >> 4) + 348;
    for (int i = 0; i < 33; i++) r += (r >> 4) + 709;
    for (int i = 0; i < 73; i++) r += (r >> 3) + 947;
    if (r > 289676) r = r % 1453;
    long arr[15];
    for (int j = 0; j < 15; j++) arr[j] = r + j;
    for (int j = 0; j < 15; j++) r += arr[j];
    return r;
}

long func_171(long a, long b) {
    long r = a + b * 56;
    for (int i = 0; i < 33; i++) r += (r >> 5) + 301;
    for (int i = 0; i < 51; i++) r += (r >> 1) + 82;
    for (int i = 0; i < 51; i++) r += (r >> 3) + 314;
    if (r > 762524) r = r % 7081;
    return r;
}

long func_172(long a, long b) {
    long r = a + b * 57;
    for (int i = 0; i < 67; i++) r += (r >> 1) + 745;
    for (int i = 0; i < 55; i++) r += (r >> 5) + 446;
    long arr[13];
    for (int j = 0; j < 13; j++) arr[j] = r + j;
    for (int j = 0; j < 13; j++) r += arr[j];
    return r;
}

long func_173(long a, long b) {
    long r = a + b * 10;
    for (int i = 0; i < 91; i++) r += (r >> 4) + 373;
    for (int i = 0; i < 75; i++) r += (r >> 2) + 976;
    for (int i = 0; i < 13; i++) r += (r >> 2) + 870;
    if (r > 829264) r = r % 7279;
    return r;
}

long func_174(long a, long b) {
    long r = a + b * 9;
    for (int i = 0; i < 92; i++) r += (r >> 3) + 371;
    if (r > 604799) r = r % 630;
    long arr[38];
    for (int j = 0; j < 38; j++) arr[j] = r + j;
    for (int j = 0; j < 38; j++) r += arr[j];
    return r;
}

long func_175(long a, long b) {
    long r = a + b * 48;
    for (int i = 0; i < 66; i++) r += (r >> 1) + 588;
    for (int i = 0; i < 27; i++) r += (r >> 5) + 376;
    if (r > 691113) r = r % 4666;
    return r;
}

long func_176(long a, long b) {
    long r = a + b * 15;
    for (int i = 0; i < 33; i++) r += (r >> 4) + 531;
    if (r > 598956) r = r % 2029;
    return r;
}

long func_177(long a, long b) {
    long r = a + b * 34;
    for (int i = 0; i < 67; i++) r += (r >> 2) + 627;
    for (int i = 0; i < 46; i++) r += (r >> 4) + 205;
    for (int i = 0; i < 25; i++) r += (r >> 2) + 874;
    return r;
}

long func_178(long a, long b) {
    long r = a + b * 92;
    for (int i = 0; i < 21; i++) r += (r >> 3) + 684;
    for (int i = 0; i < 54; i++) r += (r >> 1) + 564;
    if (r > 944629) r = r % 5014;
    long arr[50];
    for (int j = 0; j < 50; j++) arr[j] = r + j;
    for (int j = 0; j < 50; j++) r += arr[j];
    return r;
}

long func_179(long a, long b) {
    long r = a + b * 23;
    for (int i = 0; i < 75; i++) r += (r >> 2) + 125;
    for (int i = 0; i < 35; i++) r += (r >> 2) + 243;
    if (r > 37560) r = r % 6012;
    long arr[33];
    for (int j = 0; j < 33; j++) arr[j] = r + j;
    for (int j = 0; j < 33; j++) r += arr[j];
    return r;
}

long func_180(long a, long b) {
    long r = a + b * 60;
    for (int i = 0; i < 26; i++) r += (r >> 5) + 906;
    for (int i = 0; i < 21; i++) r += (r >> 1) + 317;
    for (int i = 0; i < 60; i++) r += (r >> 4) + 539;
    if (r > 439322) r = r % 9519;
    return r;
}

long func_181(long a, long b) {
    long r = a + b * 41;
    for (int i = 0; i < 19; i++) r += (r >> 4) + 478;
    for (int i = 0; i < 97; i++) r += (r >> 5) + 353;
    for (int i = 0; i < 26; i++) r += (r >> 5) + 656;
    if (r > 815077) r = r % 2214;
    return r;
}

long func_182(long a, long b) {
    long r = a + b * 8;
    for (int i = 0; i < 76; i++) r += (r >> 2) + 312;
    return r;
}

long func_183(long a, long b) {
    long r = a + b * 91;
    for (int i = 0; i < 54; i++) r += (r >> 5) + 917;
    return r;
}

long func_184(long a, long b) {
    long r = a + b * 26;
    for (int i = 0; i < 80; i++) r += (r >> 3) + 129;
    for (int i = 0; i < 90; i++) r += (r >> 3) + 630;
    for (int i = 0; i < 78; i++) r += (r >> 1) + 515;
    if (r > 630556) r = r % 9613;
    return r;
}

long func_185(long a, long b) {
    long r = a + b * 85;
    for (int i = 0; i < 87; i++) r += (r >> 3) + 863;
    for (int i = 0; i < 82; i++) r += (r >> 1) + 846;
    for (int i = 0; i < 13; i++) r += (r >> 1) + 47;
    if (r > 818475) r = r % 9549;
    return r;
}

long func_186(long a, long b) {
    long r = a + b * 27;
    for (int i = 0; i < 63; i++) r += (r >> 5) + 655;
    for (int i = 0; i < 13; i++) r += (r >> 4) + 911;
    for (int i = 0; i < 90; i++) r += (r >> 5) + 297;
    if (r > 326768) r = r % 8012;
    return r;
}

long func_187(long a, long b) {
    long r = a + b * 88;
    for (int i = 0; i < 48; i++) r += (r >> 4) + 75;
    for (int i = 0; i < 98; i++) r += (r >> 1) + 162;
    if (r > 517774) r = r % 7709;
    return r;
}

long func_188(long a, long b) {
    long r = a + b * 78;
    for (int i = 0; i < 50; i++) r += (r >> 3) + 752;
    if (r > 372147) r = r % 6632;
    return r;
}

long func_189(long a, long b) {
    long r = a + b * 48;
    for (int i = 0; i < 81; i++) r += (r >> 1) + 327;
    for (int i = 0; i < 40; i++) r += (r >> 4) + 126;
    for (int i = 0; i < 44; i++) r += (r >> 4) + 254;
    return r;
}

long func_190(long a, long b) {
    long r = a + b * 50;
    for (int i = 0; i < 63; i++) r += (r >> 2) + 986;
    for (int i = 0; i < 30; i++) r += (r >> 3) + 957;
    for (int i = 0; i < 83; i++) r += (r >> 3) + 195;
    if (r > 532469) r = r % 8533;
    return r;
}

long func_191(long a, long b) {
    long r = a + b * 40;
    for (int i = 0; i < 12; i++) r += (r >> 1) + 968;
    for (int i = 0; i < 60; i++) r += (r >> 5) + 469;
    if (r > 235595) r = r % 9657;
    return r;
}

long func_192(long a, long b) {
    long r = a + b * 7;
    for (int i = 0; i < 73; i++) r += (r >> 5) + 904;
    for (int i = 0; i < 93; i++) r += (r >> 4) + 293;
    if (r > 898324) r = r % 1861;
    return r;
}

long func_193(long a, long b) {
    long r = a + b * 34;
    for (int i = 0; i < 56; i++) r += (r >> 4) + 375;
    for (int i = 0; i < 15; i++) r += (r >> 4) + 53;
    for (int i = 0; i < 82; i++) r += (r >> 5) + 200;
    if (r > 312620) r = r % 1304;
    return r;
}

long func_194(long a, long b) {
    long r = a + b * 58;
    for (int i = 0; i < 45; i++) r += (r >> 5) + 697;
    for (int i = 0; i < 88; i++) r += (r >> 1) + 132;
    for (int i = 0; i < 22; i++) r += (r >> 4) + 383;
    if (r > 365556) r = r % 9239;
    long arr[19];
    for (int j = 0; j < 19; j++) arr[j] = r + j;
    for (int j = 0; j < 19; j++) r += arr[j];
    return r;
}

long func_195(long a, long b) {
    long r = a + b * 26;
    for (int i = 0; i < 75; i++) r += (r >> 4) + 513;
    for (int i = 0; i < 15; i++) r += (r >> 1) + 40;
    for (int i = 0; i < 27; i++) r += (r >> 3) + 824;
    if (r > 489187) r = r % 2540;
    long arr[42];
    for (int j = 0; j < 42; j++) arr[j] = r + j;
    for (int j = 0; j < 42; j++) r += arr[j];
    return r;
}

long func_196(long a, long b) {
    long r = a + b * 18;
    for (int i = 0; i < 88; i++) r += (r >> 3) + 167;
    for (int i = 0; i < 60; i++) r += (r >> 5) + 758;
    if (r > 632565) r = r % 5611;
    long arr[42];
    for (int j = 0; j < 42; j++) arr[j] = r + j;
    for (int j = 0; j < 42; j++) r += arr[j];
    return r;
}

long func_197(long a, long b) {
    long r = a + b * 69;
    for (int i = 0; i < 100; i++) r += (r >> 5) + 307;
    for (int i = 0; i < 70; i++) r += (r >> 1) + 378;
    if (r > 124928) r = r % 6924;
    long arr[50];
    for (int j = 0; j < 50; j++) arr[j] = r + j;
    for (int j = 0; j < 50; j++) r += arr[j];
    return r;
}

long func_198(long a, long b) {
    long r = a + b * 4;
    for (int i = 0; i < 70; i++) r += (r >> 3) + 991;
    for (int i = 0; i < 93; i++) r += (r >> 5) + 592;
    for (int i = 0; i < 39; i++) r += (r >> 1) + 598;
    if (r > 559697) r = r % 6329;
    return r;
}

long func_199(long a, long b) {
    long r = a + b * 88;
    for (int i = 0; i < 14; i++) r += (r >> 5) + 971;
    if (r > 210051) r = r % 410;
    return r;
}

long func_200(long a, long b) {
    long r = a + b * 54;
    for (int i = 0; i < 62; i++) r += (r >> 2) + 421;
    if (r > 651181) r = r % 7826;
    long arr[13];
    for (int j = 0; j < 13; j++) arr[j] = r + j;
    for (int j = 0; j < 13; j++) r += arr[j];
    return r;
}

long func_201(long a, long b) {
    long r = a + b * 91;
    for (int i = 0; i < 76; i++) r += (r >> 2) + 575;
    if (r > 704395) r = r % 7937;
    long arr[30];
    for (int j = 0; j < 30; j++) arr[j] = r + j;
    for (int j = 0; j < 30; j++) r += arr[j];
    return r;
}

long func_202(long a, long b) {
    long r = a + b * 23;
    for (int i = 0; i < 78; i++) r += (r >> 3) + 560;
    for (int i = 0; i < 55; i++) r += (r >> 3) + 625;
    if (r > 268494) r = r % 4671;
    long arr[24];
    for (int j = 0; j < 24; j++) arr[j] = r + j;
    for (int j = 0; j < 24; j++) r += arr[j];
    return r;
}

long func_203(long a, long b) {
    long r = a + b * 39;
    for (int i = 0; i < 100; i++) r += (r >> 2) + 707;
    for (int i = 0; i < 100; i++) r += (r >> 4) + 325;
    if (r > 597713) r = r % 4580;
    return r;
}

long func_204(long a, long b) {
    long r = a + b * 74;
    for (int i = 0; i < 79; i++) r += (r >> 4) + 918;
    for (int i = 0; i < 60; i++) r += (r >> 3) + 978;
    for (int i = 0; i < 28; i++) r += (r >> 3) + 44;
    long arr[32];
    for (int j = 0; j < 32; j++) arr[j] = r + j;
    for (int j = 0; j < 32; j++) r += arr[j];
    return r;
}

long func_205(long a, long b) {
    long r = a + b * 57;
    for (int i = 0; i < 42; i++) r += (r >> 4) + 220;
    for (int i = 0; i < 35; i++) r += (r >> 5) + 278;
    for (int i = 0; i < 81; i++) r += (r >> 3) + 141;
    long arr[25];
    for (int j = 0; j < 25; j++) arr[j] = r + j;
    for (int j = 0; j < 25; j++) r += arr[j];
    return r;
}

long func_206(long a, long b) {
    long r = a + b * 32;
    for (int i = 0; i < 95; i++) r += (r >> 5) + 232;
    if (r > 65040) r = r % 1741;
    return r;
}

long func_207(long a, long b) {
    long r = a + b * 92;
    for (int i = 0; i < 22; i++) r += (r >> 2) + 6;
    for (int i = 0; i < 80; i++) r += (r >> 2) + 417;
    if (r > 933425) r = r % 7893;
    return r;
}

long func_208(long a, long b) {
    long r = a + b * 26;
    for (int i = 0; i < 51; i++) r += (r >> 3) + 662;
    for (int i = 0; i < 17; i++) r += (r >> 1) + 668;
    if (r > 571147) r = r % 711;
    long arr[21];
    for (int j = 0; j < 21; j++) arr[j] = r + j;
    for (int j = 0; j < 21; j++) r += arr[j];
    return r;
}

long func_209(long a, long b) {
    long r = a + b * 54;
    for (int i = 0; i < 14; i++) r += (r >> 4) + 807;
    if (r > 992105) r = r % 4842;
    long arr[10];
    for (int j = 0; j < 10; j++) arr[j] = r + j;
    for (int j = 0; j < 10; j++) r += arr[j];
    return r;
}

long func_210(long a, long b) {
    long r = a + b * 39;
    for (int i = 0; i < 87; i++) r += (r >> 1) + 951;
    for (int i = 0; i < 52; i++) r += (r >> 3) + 466;
    for (int i = 0; i < 92; i++) r += (r >> 5) + 537;
    if (r > 994152) r = r % 2298;
    long arr[39];
    for (int j = 0; j < 39; j++) arr[j] = r + j;
    for (int j = 0; j < 39; j++) r += arr[j];
    return r;
}

long func_211(long a, long b) {
    long r = a + b * 35;
    for (int i = 0; i < 24; i++) r += (r >> 3) + 167;
    if (r > 689776) r = r % 4315;
    long arr[10];
    for (int j = 0; j < 10; j++) arr[j] = r + j;
    for (int j = 0; j < 10; j++) r += arr[j];
    return r;
}

long func_212(long a, long b) {
    long r = a + b * 95;
    for (int i = 0; i < 47; i++) r += (r >> 5) + 691;
    for (int i = 0; i < 34; i++) r += (r >> 2) + 626;
    if (r > 950617) r = r % 6743;
    long arr[42];
    for (int j = 0; j < 42; j++) arr[j] = r + j;
    for (int j = 0; j < 42; j++) r += arr[j];
    return r;
}

long func_213(long a, long b) {
    long r = a + b * 42;
    for (int i = 0; i < 61; i++) r += (r >> 1) + 190;
    if (r > 510646) r = r % 5401;
    long arr[10];
    for (int j = 0; j < 10; j++) arr[j] = r + j;
    for (int j = 0; j < 10; j++) r += arr[j];
    return r;
}

long func_214(long a, long b) {
    long r = a + b * 34;
    for (int i = 0; i < 40; i++) r += (r >> 4) + 772;
    for (int i = 0; i < 44; i++) r += (r >> 3) + 310;
    if (r > 610705) r = r % 287;
    return r;
}

long func_215(long a, long b) {
    long r = a + b * 47;
    for (int i = 0; i < 40; i++) r += (r >> 1) + 684;
    for (int i = 0; i < 25; i++) r += (r >> 4) + 315;
    for (int i = 0; i < 30; i++) r += (r >> 4) + 703;
    if (r > 948599) r = r % 5195;
    long arr[50];
    for (int j = 0; j < 50; j++) arr[j] = r + j;
    for (int j = 0; j < 50; j++) r += arr[j];
    return r;
}

long func_216(long a, long b) {
    long r = a + b * 38;
    for (int i = 0; i < 88; i++) r += (r >> 2) + 225;
    for (int i = 0; i < 27; i++) r += (r >> 4) + 157;
    if (r > 645163) r = r % 6221;
    return r;
}

long func_217(long a, long b) {
    long r = a + b * 71;
    for (int i = 0; i < 78; i++) r += (r >> 2) + 781;
    for (int i = 0; i < 41; i++) r += (r >> 5) + 895;
    if (r > 561033) r = r % 7419;
    long arr[33];
    for (int j = 0; j < 33; j++) arr[j] = r + j;
    for (int j = 0; j < 33; j++) r += arr[j];
    return r;
}

long func_218(long a, long b) {
    long r = a + b * 10;
    for (int i = 0; i < 24; i++) r += (r >> 1) + 849;
    for (int i = 0; i < 80; i++) r += (r >> 5) + 208;
    for (int i = 0; i < 83; i++) r += (r >> 5) + 154;
    long arr[38];
    for (int j = 0; j < 38; j++) arr[j] = r + j;
    for (int j = 0; j < 38; j++) r += arr[j];
    return r;
}

long func_219(long a, long b) {
    long r = a + b * 15;
    for (int i = 0; i < 36; i++) r += (r >> 5) + 501;
    for (int i = 0; i < 21; i++) r += (r >> 5) + 457;
    for (int i = 0; i < 17; i++) r += (r >> 4) + 136;
    if (r > 488987) r = r % 9339;
    return r;
}

long func_220(long a, long b) {
    long r = a + b * 60;
    for (int i = 0; i < 49; i++) r += (r >> 1) + 406;
    for (int i = 0; i < 42; i++) r += (r >> 1) + 764;
    for (int i = 0; i < 37; i++) r += (r >> 5) + 75;
    return r;
}

long func_221(long a, long b) {
    long r = a + b * 9;
    for (int i = 0; i < 17; i++) r += (r >> 1) + 957;
    for (int i = 0; i < 70; i++) r += (r >> 1) + 294;
    for (int i = 0; i < 62; i++) r += (r >> 2) + 788;
    long arr[36];
    for (int j = 0; j < 36; j++) arr[j] = r + j;
    for (int j = 0; j < 36; j++) r += arr[j];
    return r;
}

long func_222(long a, long b) {
    long r = a + b * 48;
    for (int i = 0; i < 67; i++) r += (r >> 4) + 385;
    for (int i = 0; i < 20; i++) r += (r >> 5) + 137;
    if (r > 374663) r = r % 2043;
    return r;
}

long func_223(long a, long b) {
    long r = a + b * 69;
    for (int i = 0; i < 77; i++) r += (r >> 2) + 746;
    for (int i = 0; i < 38; i++) r += (r >> 1) + 775;
    return r;
}

long func_224(long a, long b) {
    long r = a + b * 87;
    for (int i = 0; i < 79; i++) r += (r >> 4) + 545;
    for (int i = 0; i < 58; i++) r += (r >> 2) + 254;
    for (int i = 0; i < 68; i++) r += (r >> 3) + 159;
    long arr[17];
    for (int j = 0; j < 17; j++) arr[j] = r + j;
    for (int j = 0; j < 17; j++) r += arr[j];
    return r;
}

long func_225(long a, long b) {
    long r = a + b * 5;
    for (int i = 0; i < 63; i++) r += (r >> 5) + 785;
    for (int i = 0; i < 12; i++) r += (r >> 2) + 212;
    for (int i = 0; i < 18; i++) r += (r >> 1) + 609;
    long arr[13];
    for (int j = 0; j < 13; j++) arr[j] = r + j;
    for (int j = 0; j < 13; j++) r += arr[j];
    return r;
}

long func_226(long a, long b) {
    long r = a + b * 32;
    for (int i = 0; i < 15; i++) r += (r >> 4) + 450;
    for (int i = 0; i < 39; i++) r += (r >> 5) + 223;
    for (int i = 0; i < 17; i++) r += (r >> 2) + 516;
    if (r > 255536) r = r % 9538;
    return r;
}

long func_227(long a, long b) {
    long r = a + b * 77;
    for (int i = 0; i < 51; i++) r += (r >> 2) + 310;
    for (int i = 0; i < 28; i++) r += (r >> 5) + 227;
    for (int i = 0; i < 62; i++) r += (r >> 3) + 282;
    long arr[21];
    for (int j = 0; j < 21; j++) arr[j] = r + j;
    for (int j = 0; j < 21; j++) r += arr[j];
    return r;
}

long func_228(long a, long b) {
    long r = a + b * 81;
    for (int i = 0; i < 64; i++) r += (r >> 5) + 508;
    for (int i = 0; i < 16; i++) r += (r >> 3) + 965;
    for (int i = 0; i < 92; i++) r += (r >> 4) + 805;
    if (r > 740132) r = r % 6921;
    return r;
}

long func_229(long a, long b) {
    long r = a + b * 39;
    for (int i = 0; i < 33; i++) r += (r >> 5) + 485;
    for (int i = 0; i < 40; i++) r += (r >> 2) + 308;
    if (r > 161363) r = r % 7686;
    long arr[45];
    for (int j = 0; j < 45; j++) arr[j] = r + j;
    for (int j = 0; j < 45; j++) r += arr[j];
    return r;
}

long func_230(long a, long b) {
    long r = a + b * 53;
    for (int i = 0; i < 81; i++) r += (r >> 5) + 138;
    for (int i = 0; i < 59; i++) r += (r >> 2) + 262;
    long arr[38];
    for (int j = 0; j < 38; j++) arr[j] = r + j;
    for (int j = 0; j < 38; j++) r += arr[j];
    return r;
}

long func_231(long a, long b) {
    long r = a + b * 48;
    for (int i = 0; i < 78; i++) r += (r >> 2) + 53;
    long arr[48];
    for (int j = 0; j < 48; j++) arr[j] = r + j;
    for (int j = 0; j < 48; j++) r += arr[j];
    return r;
}

long func_232(long a, long b) {
    long r = a + b * 6;
    for (int i = 0; i < 34; i++) r += (r >> 5) + 742;
    if (r > 237558) r = r % 7954;
    return r;
}

long func_233(long a, long b) {
    long r = a + b * 43;
    for (int i = 0; i < 11; i++) r += (r >> 2) + 960;
    for (int i = 0; i < 34; i++) r += (r >> 1) + 765;
    if (r > 512184) r = r % 4074;
    long arr[23];
    for (int j = 0; j < 23; j++) arr[j] = r + j;
    for (int j = 0; j < 23; j++) r += arr[j];
    return r;
}

long func_234(long a, long b) {
    long r = a + b * 51;
    for (int i = 0; i < 80; i++) r += (r >> 3) + 795;
    return r;
}

long func_235(long a, long b) {
    long r = a + b * 84;
    for (int i = 0; i < 49; i++) r += (r >> 3) + 369;
    for (int i = 0; i < 75; i++) r += (r >> 4) + 478;
    long arr[40];
    for (int j = 0; j < 40; j++) arr[j] = r + j;
    for (int j = 0; j < 40; j++) r += arr[j];
    return r;
}

long func_236(long a, long b) {
    long r = a + b * 98;
    for (int i = 0; i < 36; i++) r += (r >> 3) + 321;
    for (int i = 0; i < 62; i++) r += (r >> 1) + 577;
    if (r > 787259) r = r % 2490;
    return r;
}

long func_237(long a, long b) {
    long r = a + b * 71;
    for (int i = 0; i < 84; i++) r += (r >> 4) + 303;
    for (int i = 0; i < 29; i++) r += (r >> 2) + 338;
    for (int i = 0; i < 39; i++) r += (r >> 4) + 584;
    if (r > 533555) r = r % 9121;
    long arr[31];
    for (int j = 0; j < 31; j++) arr[j] = r + j;
    for (int j = 0; j < 31; j++) r += arr[j];
    return r;
}

long func_238(long a, long b) {
    long r = a + b * 33;
    for (int i = 0; i < 92; i++) r += (r >> 4) + 472;
    for (int i = 0; i < 31; i++) r += (r >> 3) + 174;
    long arr[21];
    for (int j = 0; j < 21; j++) arr[j] = r + j;
    for (int j = 0; j < 21; j++) r += arr[j];
    return r;
}

long func_239(long a, long b) {
    long r = a + b * 70;
    for (int i = 0; i < 17; i++) r += (r >> 5) + 35;
    for (int i = 0; i < 19; i++) r += (r >> 1) + 783;
    for (int i = 0; i < 10; i++) r += (r >> 4) + 141;
    if (r > 252675) r = r % 1213;
    long arr[10];
    for (int j = 0; j < 10; j++) arr[j] = r + j;
    for (int j = 0; j < 10; j++) r += arr[j];
    return r;
}

long func_240(long a, long b) {
    long r = a + b * 28;
    for (int i = 0; i < 68; i++) r += (r >> 3) + 62;
    for (int i = 0; i < 89; i++) r += (r >> 5) + 935;
    for (int i = 0; i < 71; i++) r += (r >> 4) + 17;
    long arr[10];
    for (int j = 0; j < 10; j++) arr[j] = r + j;
    for (int j = 0; j < 10; j++) r += arr[j];
    return r;
}

long func_241(long a, long b) {
    long r = a + b * 3;
    for (int i = 0; i < 45; i++) r += (r >> 5) + 294;
    for (int i = 0; i < 12; i++) r += (r >> 5) + 833;
    for (int i = 0; i < 99; i++) r += (r >> 4) + 826;
    if (r > 197974) r = r % 1853;
    long arr[43];
    for (int j = 0; j < 43; j++) arr[j] = r + j;
    for (int j = 0; j < 43; j++) r += arr[j];
    return r;
}

long func_242(long a, long b) {
    long r = a + b * 20;
    for (int i = 0; i < 34; i++) r += (r >> 5) + 540;
    return r;
}

long func_243(long a, long b) {
    long r = a + b * 51;
    for (int i = 0; i < 57; i++) r += (r >> 4) + 471;
    if (r > 741105) r = r % 3800;
    return r;
}

long func_244(long a, long b) {
    long r = a + b * 11;
    for (int i = 0; i < 93; i++) r += (r >> 1) + 96;
    for (int i = 0; i < 61; i++) r += (r >> 4) + 387;
    for (int i = 0; i < 80; i++) r += (r >> 4) + 58;
    if (r > 746986) r = r % 2907;
    return r;
}

long func_245(long a, long b) {
    long r = a + b * 56;
    for (int i = 0; i < 52; i++) r += (r >> 5) + 879;
    for (int i = 0; i < 22; i++) r += (r >> 5) + 942;
    for (int i = 0; i < 15; i++) r += (r >> 2) + 217;
    if (r > 735916) r = r % 9386;
    return r;
}

long func_246(long a, long b) {
    long r = a + b * 6;
    for (int i = 0; i < 97; i++) r += (r >> 3) + 921;
    if (r > 700077) r = r % 639;
    return r;
}

long func_247(long a, long b) {
    long r = a + b * 41;
    for (int i = 0; i < 36; i++) r += (r >> 5) + 148;
    if (r > 757332) r = r % 6625;
    long arr[29];
    for (int j = 0; j < 29; j++) arr[j] = r + j;
    for (int j = 0; j < 29; j++) r += arr[j];
    return r;
}

long func_248(long a, long b) {
    long r = a + b * 21;
    for (int i = 0; i < 40; i++) r += (r >> 5) + 855;
    for (int i = 0; i < 59; i++) r += (r >> 5) + 340;
    for (int i = 0; i < 59; i++) r += (r >> 2) + 810;
    if (r > 769340) r = r % 1384;
    long arr[32];
    for (int j = 0; j < 32; j++) arr[j] = r + j;
    for (int j = 0; j < 32; j++) r += arr[j];
    return r;
}

long func_249(long a, long b) {
    long r = a + b * 7;
    for (int i = 0; i < 65; i++) r += (r >> 2) + 859;
    long arr[49];
    for (int j = 0; j < 49; j++) arr[j] = r + j;
    for (int j = 0; j < 49; j++) r += arr[j];
    return r;
}

long func_250(long a, long b) {
    long r = a + b * 77;
    for (int i = 0; i < 51; i++) r += (r >> 1) + 650;
    for (int i = 0; i < 44; i++) r += (r >> 4) + 503;
    long arr[34];
    for (int j = 0; j < 34; j++) arr[j] = r + j;
    for (int j = 0; j < 34; j++) r += arr[j];
    return r;
}

long func_251(long a, long b) {
    long r = a + b * 56;
    for (int i = 0; i < 97; i++) r += (r >> 5) + 677;
    if (r > 819676) r = r % 4939;
    long arr[14];
    for (int j = 0; j < 14; j++) arr[j] = r + j;
    for (int j = 0; j < 14; j++) r += arr[j];
    return r;
}

long func_252(long a, long b) {
    long r = a + b * 11;
    for (int i = 0; i < 29; i++) r += (r >> 4) + 729;
    for (int i = 0; i < 91; i++) r += (r >> 2) + 758;
    if (r > 388221) r = r % 1845;
    return r;
}

long func_253(long a, long b) {
    long r = a + b * 40;
    for (int i = 0; i < 56; i++) r += (r >> 3) + 105;
    for (int i = 0; i < 26; i++) r += (r >> 1) + 192;
    if (r > 594041) r = r % 9188;
    long arr[16];
    for (int j = 0; j < 16; j++) arr[j] = r + j;
    for (int j = 0; j < 16; j++) r += arr[j];
    return r;
}

long func_254(long a, long b) {
    long r = a + b * 4;
    for (int i = 0; i < 55; i++) r += (r >> 5) + 96;
    if (r > 832543) r = r % 5415;
    long arr[10];
    for (int j = 0; j < 10; j++) arr[j] = r + j;
    for (int j = 0; j < 10; j++) r += arr[j];
    return r;
}

long func_255(long a, long b) {
    long r = a + b * 38;
    for (int i = 0; i < 59; i++) r += (r >> 1) + 743;
    for (int i = 0; i < 81; i++) r += (r >> 2) + 586;
    if (r > 728605) r = r % 6337;
    return r;
}

long func_256(long a, long b) {
    long r = a + b * 35;
    for (int i = 0; i < 44; i++) r += (r >> 4) + 150;
    for (int i = 0; i < 18; i++) r += (r >> 2) + 446;
    return r;
}

long func_257(long a, long b) {
    long r = a + b * 10;
    for (int i = 0; i < 42; i++) r += (r >> 2) + 739;
    for (int i = 0; i < 90; i++) r += (r >> 4) + 609;
    if (r > 490102) r = r % 1852;
    return r;
}

long func_258(long a, long b) {
    long r = a + b * 1;
    for (int i = 0; i < 52; i++) r += (r >> 5) + 390;
    for (int i = 0; i < 52; i++) r += (r >> 4) + 343;
    if (r > 873539) r = r % 9838;
    return r;
}

long func_259(long a, long b) {
    long r = a + b * 42;
    for (int i = 0; i < 98; i++) r += (r >> 2) + 491;
    for (int i = 0; i < 50; i++) r += (r >> 2) + 988;
    for (int i = 0; i < 60; i++) r += (r >> 3) + 299;
    if (r > 673646) r = r % 8144;
    long arr[25];
    for (int j = 0; j < 25; j++) arr[j] = r + j;
    for (int j = 0; j < 25; j++) r += arr[j];
    return r;
}

long func_260(long a, long b) {
    long r = a + b * 42;
    for (int i = 0; i < 45; i++) r += (r >> 4) + 374;
    for (int i = 0; i < 24; i++) r += (r >> 5) + 205;
    if (r > 582133) r = r % 3047;
    long arr[45];
    for (int j = 0; j < 45; j++) arr[j] = r + j;
    for (int j = 0; j < 45; j++) r += arr[j];
    return r;
}

long func_261(long a, long b) {
    long r = a + b * 4;
    for (int i = 0; i < 69; i++) r += (r >> 2) + 449;
    for (int i = 0; i < 47; i++) r += (r >> 1) + 839;
    for (int i = 0; i < 62; i++) r += (r >> 4) + 143;
    if (r > 263777) r = r % 4239;
    long arr[37];
    for (int j = 0; j < 37; j++) arr[j] = r + j;
    for (int j = 0; j < 37; j++) r += arr[j];
    return r;
}

long func_262(long a, long b) {
    long r = a + b * 49;
    for (int i = 0; i < 67; i++) r += (r >> 5) + 491;
    if (r > 570324) r = r % 8400;
    long arr[36];
    for (int j = 0; j < 36; j++) arr[j] = r + j;
    for (int j = 0; j < 36; j++) r += arr[j];
    return r;
}

long func_263(long a, long b) {
    long r = a + b * 70;
    for (int i = 0; i < 56; i++) r += (r >> 5) + 609;
    if (r > 99110) r = r % 1891;
    long arr[32];
    for (int j = 0; j < 32; j++) arr[j] = r + j;
    for (int j = 0; j < 32; j++) r += arr[j];
    return r;
}

long func_264(long a, long b) {
    long r = a + b * 22;
    for (int i = 0; i < 88; i++) r += (r >> 1) + 577;
    for (int i = 0; i < 92; i++) r += (r >> 4) + 991;
    for (int i = 0; i < 52; i++) r += (r >> 4) + 109;
    return r;
}

long func_265(long a, long b) {
    long r = a + b * 66;
    for (int i = 0; i < 76; i++) r += (r >> 5) + 595;
    for (int i = 0; i < 98; i++) r += (r >> 5) + 227;
    for (int i = 0; i < 67; i++) r += (r >> 3) + 401;
    if (r > 722565) r = r % 9743;
    long arr[19];
    for (int j = 0; j < 19; j++) arr[j] = r + j;
    for (int j = 0; j < 19; j++) r += arr[j];
    return r;
}

long func_266(long a, long b) {
    long r = a + b * 45;
    for (int i = 0; i < 71; i++) r += (r >> 1) + 303;
    if (r > 100025) r = r % 2001;
    long arr[19];
    for (int j = 0; j < 19; j++) arr[j] = r + j;
    for (int j = 0; j < 19; j++) r += arr[j];
    return r;
}

long func_267(long a, long b) {
    long r = a + b * 45;
    for (int i = 0; i < 53; i++) r += (r >> 4) + 804;
    for (int i = 0; i < 36; i++) r += (r >> 5) + 495;
    if (r > 112365) r = r % 7278;
    long arr[38];
    for (int j = 0; j < 38; j++) arr[j] = r + j;
    for (int j = 0; j < 38; j++) r += arr[j];
    return r;
}

long func_268(long a, long b) {
    long r = a + b * 41;
    for (int i = 0; i < 48; i++) r += (r >> 1) + 830;
    if (r > 33682) r = r % 5720;
    long arr[20];
    for (int j = 0; j < 20; j++) arr[j] = r + j;
    for (int j = 0; j < 20; j++) r += arr[j];
    return r;
}

long func_269(long a, long b) {
    long r = a + b * 95;
    for (int i = 0; i < 76; i++) r += (r >> 2) + 566;
    long arr[39];
    for (int j = 0; j < 39; j++) arr[j] = r + j;
    for (int j = 0; j < 39; j++) r += arr[j];
    return r;
}

long func_270(long a, long b) {
    long r = a + b * 30;
    for (int i = 0; i < 90; i++) r += (r >> 2) + 191;
    for (int i = 0; i < 91; i++) r += (r >> 4) + 406;
    long arr[22];
    for (int j = 0; j < 22; j++) arr[j] = r + j;
    for (int j = 0; j < 22; j++) r += arr[j];
    return r;
}

long func_271(long a, long b) {
    long r = a + b * 58;
    for (int i = 0; i < 64; i++) r += (r >> 4) + 5;
    for (int i = 0; i < 100; i++) r += (r >> 2) + 211;
    for (int i = 0; i < 45; i++) r += (r >> 1) + 592;
    long arr[21];
    for (int j = 0; j < 21; j++) arr[j] = r + j;
    for (int j = 0; j < 21; j++) r += arr[j];
    return r;
}

long func_272(long a, long b) {
    long r = a + b * 47;
    for (int i = 0; i < 35; i++) r += (r >> 4) + 117;
    for (int i = 0; i < 43; i++) r += (r >> 4) + 541;
    if (r > 338628) r = r % 9880;
    return r;
}

long func_273(long a, long b) {
    long r = a + b * 51;
    for (int i = 0; i < 24; i++) r += (r >> 3) + 361;
    for (int i = 0; i < 68; i++) r += (r >> 5) + 177;
    for (int i = 0; i < 96; i++) r += (r >> 3) + 941;
    if (r > 98868) r = r % 2294;
    return r;
}

long func_274(long a, long b) {
    long r = a + b * 31;
    for (int i = 0; i < 24; i++) r += (r >> 2) + 383;
    for (int i = 0; i < 98; i++) r += (r >> 2) + 524;
    if (r > 635397) r = r % 2358;
    long arr[37];
    for (int j = 0; j < 37; j++) arr[j] = r + j;
    for (int j = 0; j < 37; j++) r += arr[j];
    return r;
}

long func_275(long a, long b) {
    long r = a + b * 24;
    for (int i = 0; i < 91; i++) r += (r >> 5) + 711;
    for (int i = 0; i < 92; i++) r += (r >> 2) + 569;
    return r;
}

long func_276(long a, long b) {
    long r = a + b * 24;
    for (int i = 0; i < 67; i++) r += (r >> 5) + 55;
    for (int i = 0; i < 55; i++) r += (r >> 1) + 497;
    long arr[45];
    for (int j = 0; j < 45; j++) arr[j] = r + j;
    for (int j = 0; j < 45; j++) r += arr[j];
    return r;
}

long func_277(long a, long b) {
    long r = a + b * 65;
    for (int i = 0; i < 73; i++) r += (r >> 4) + 702;
    for (int i = 0; i < 72; i++) r += (r >> 4) + 728;
    for (int i = 0; i < 66; i++) r += (r >> 4) + 172;
    return r;
}

long func_278(long a, long b) {
    long r = a + b * 98;
    for (int i = 0; i < 47; i++) r += (r >> 1) + 282;
    return r;
}

long func_279(long a, long b) {
    long r = a + b * 59;
    for (int i = 0; i < 73; i++) r += (r >> 5) + 524;
    for (int i = 0; i < 24; i++) r += (r >> 5) + 117;
    for (int i = 0; i < 44; i++) r += (r >> 5) + 844;
    if (r > 578373) r = r % 781;
    long arr[38];
    for (int j = 0; j < 38; j++) arr[j] = r + j;
    for (int j = 0; j < 38; j++) r += arr[j];
    return r;
}

long func_280(long a, long b) {
    long r = a + b * 70;
    for (int i = 0; i < 64; i++) r += (r >> 1) + 754;
    if (r > 797842) r = r % 4155;
    return r;
}

long func_281(long a, long b) {
    long r = a + b * 5;
    for (int i = 0; i < 43; i++) r += (r >> 3) + 883;
    for (int i = 0; i < 21; i++) r += (r >> 4) + 887;
    if (r > 823308) r = r % 3982;
    return r;
}

long func_282(long a, long b) {
    long r = a + b * 95;
    for (int i = 0; i < 98; i++) r += (r >> 3) + 882;
    for (int i = 0; i < 100; i++) r += (r >> 5) + 648;
    for (int i = 0; i < 64; i++) r += (r >> 2) + 631;
    return r;
}

long func_283(long a, long b) {
    long r = a + b * 27;
    for (int i = 0; i < 82; i++) r += (r >> 3) + 546;
    long arr[30];
    for (int j = 0; j < 30; j++) arr[j] = r + j;
    for (int j = 0; j < 30; j++) r += arr[j];
    return r;
}

long func_284(long a, long b) {
    long r = a + b * 91;
    for (int i = 0; i < 47; i++) r += (r >> 5) + 274;
    for (int i = 0; i < 75; i++) r += (r >> 1) + 139;
    if (r > 833856) r = r % 6843;
    long arr[27];
    for (int j = 0; j < 27; j++) arr[j] = r + j;
    for (int j = 0; j < 27; j++) r += arr[j];
    return r;
}

long func_285(long a, long b) {
    long r = a + b * 84;
    for (int i = 0; i < 99; i++) r += (r >> 2) + 256;
    return r;
}

long func_286(long a, long b) {
    long r = a + b * 32;
    for (int i = 0; i < 60; i++) r += (r >> 4) + 146;
    for (int i = 0; i < 83; i++) r += (r >> 3) + 643;
    for (int i = 0; i < 63; i++) r += (r >> 4) + 463;
    long arr[15];
    for (int j = 0; j < 15; j++) arr[j] = r + j;
    for (int j = 0; j < 15; j++) r += arr[j];
    return r;
}

long func_287(long a, long b) {
    long r = a + b * 52;
    for (int i = 0; i < 45; i++) r += (r >> 3) + 466;
    for (int i = 0; i < 72; i++) r += (r >> 3) + 596;
    for (int i = 0; i < 10; i++) r += (r >> 1) + 749;
    if (r > 675678) r = r % 5969;
    long arr[44];
    for (int j = 0; j < 44; j++) arr[j] = r + j;
    for (int j = 0; j < 44; j++) r += arr[j];
    return r;
}

long func_288(long a, long b) {
    long r = a + b * 51;
    for (int i = 0; i < 64; i++) r += (r >> 2) + 507;
    long arr[31];
    for (int j = 0; j < 31; j++) arr[j] = r + j;
    for (int j = 0; j < 31; j++) r += arr[j];
    return r;
}

long func_289(long a, long b) {
    long r = a + b * 71;
    for (int i = 0; i < 26; i++) r += (r >> 5) + 873;
    for (int i = 0; i < 72; i++) r += (r >> 3) + 916;
    for (int i = 0; i < 97; i++) r += (r >> 1) + 48;
    long arr[39];
    for (int j = 0; j < 39; j++) arr[j] = r + j;
    for (int j = 0; j < 39; j++) r += arr[j];
    return r;
}

long func_290(long a, long b) {
    long r = a + b * 3;
    for (int i = 0; i < 30; i++) r += (r >> 4) + 468;
    long arr[22];
    for (int j = 0; j < 22; j++) arr[j] = r + j;
    for (int j = 0; j < 22; j++) r += arr[j];
    return r;
}

long func_291(long a, long b) {
    long r = a + b * 89;
    for (int i = 0; i < 93; i++) r += (r >> 3) + 163;
    if (r > 929176) r = r % 4589;
    return r;
}

long func_292(long a, long b) {
    long r = a + b * 47;
    for (int i = 0; i < 20; i++) r += (r >> 3) + 681;
    for (int i = 0; i < 93; i++) r += (r >> 2) + 54;
    if (r > 330349) r = r % 3936;
    return r;
}

long func_293(long a, long b) {
    long r = a + b * 12;
    for (int i = 0; i < 22; i++) r += (r >> 1) + 219;
    for (int i = 0; i < 71; i++) r += (r >> 1) + 136;
    for (int i = 0; i < 85; i++) r += (r >> 2) + 532;
    if (r > 19738) r = r % 232;
    long arr[17];
    for (int j = 0; j < 17; j++) arr[j] = r + j;
    for (int j = 0; j < 17; j++) r += arr[j];
    return r;
}

long func_294(long a, long b) {
    long r = a + b * 55;
    for (int i = 0; i < 26; i++) r += (r >> 4) + 73;
    for (int i = 0; i < 39; i++) r += (r >> 4) + 92;
    for (int i = 0; i < 23; i++) r += (r >> 1) + 321;
    if (r > 323791) r = r % 2346;
    return r;
}

long func_295(long a, long b) {
    long r = a + b * 97;
    for (int i = 0; i < 92; i++) r += (r >> 2) + 71;
    if (r > 18886) r = r % 2788;
    return r;
}

long func_296(long a, long b) {
    long r = a + b * 93;
    for (int i = 0; i < 90; i++) r += (r >> 2) + 942;
    if (r > 729916) r = r % 7348;
    long arr[15];
    for (int j = 0; j < 15; j++) arr[j] = r + j;
    for (int j = 0; j < 15; j++) r += arr[j];
    return r;
}

long func_297(long a, long b) {
    long r = a + b * 13;
    for (int i = 0; i < 25; i++) r += (r >> 5) + 748;
    if (r > 460246) r = r % 5252;
    long arr[25];
    for (int j = 0; j < 25; j++) arr[j] = r + j;
    for (int j = 0; j < 25; j++) r += arr[j];
    return r;
}

long func_298(long a, long b) {
    long r = a + b * 36;
    for (int i = 0; i < 20; i++) r += (r >> 2) + 567;
    for (int i = 0; i < 86; i++) r += (r >> 5) + 739;
    for (int i = 0; i < 87; i++) r += (r >> 3) + 798;
    if (r > 38127) r = r % 5042;
    return r;
}

long func_299(long a, long b) {
    long r = a + b * 78;
    for (int i = 0; i < 34; i++) r += (r >> 4) + 303;
    for (int i = 0; i < 92; i++) r += (r >> 1) + 803;
    for (int i = 0; i < 40; i++) r += (r >> 4) + 396;
    return r;
}

long func_300(long a, long b) {
    long r = a + b * 77;
    for (int i = 0; i < 77; i++) r += (r >> 1) + 370;
    if (r > 148394) r = r % 6437;
    long arr[46];
    for (int j = 0; j < 46; j++) arr[j] = r + j;
    for (int j = 0; j < 46; j++) r += arr[j];
    return r;
}

long func_301(long a, long b) {
    long r = a + b * 54;
    for (int i = 0; i < 79; i++) r += (r >> 2) + 782;
    for (int i = 0; i < 70; i++) r += (r >> 1) + 18;
    if (r > 24463) r = r % 4395;
    return r;
}

long func_302(long a, long b) {
    long r = a + b * 8;
    for (int i = 0; i < 74; i++) r += (r >> 3) + 644;
    for (int i = 0; i < 74; i++) r += (r >> 4) + 434;
    if (r > 96431) r = r % 8891;
    long arr[19];
    for (int j = 0; j < 19; j++) arr[j] = r + j;
    for (int j = 0; j < 19; j++) r += arr[j];
    return r;
}

long func_303(long a, long b) {
    long r = a + b * 36;
    for (int i = 0; i < 49; i++) r += (r >> 1) + 524;
    if (r > 857312) r = r % 2645;
    long arr[35];
    for (int j = 0; j < 35; j++) arr[j] = r + j;
    for (int j = 0; j < 35; j++) r += arr[j];
    return r;
}

long func_304(long a, long b) {
    long r = a + b * 76;
    for (int i = 0; i < 93; i++) r += (r >> 1) + 318;
    for (int i = 0; i < 99; i++) r += (r >> 4) + 748;
    for (int i = 0; i < 40; i++) r += (r >> 1) + 251;
    return r;
}

long func_305(long a, long b) {
    long r = a + b * 59;
    for (int i = 0; i < 87; i++) r += (r >> 1) + 317;
    for (int i = 0; i < 95; i++) r += (r >> 2) + 123;
    for (int i = 0; i < 11; i++) r += (r >> 2) + 719;
    return r;
}

long func_306(long a, long b) {
    long r = a + b * 45;
    for (int i = 0; i < 76; i++) r += (r >> 3) + 171;
    for (int i = 0; i < 57; i++) r += (r >> 2) + 768;
    for (int i = 0; i < 44; i++) r += (r >> 1) + 790;
    if (r > 361284) r = r % 7134;
    return r;
}

long func_307(long a, long b) {
    long r = a + b * 9;
    for (int i = 0; i < 83; i++) r += (r >> 1) + 509;
    for (int i = 0; i < 68; i++) r += (r >> 5) + 369;
    long arr[20];
    for (int j = 0; j < 20; j++) arr[j] = r + j;
    for (int j = 0; j < 20; j++) r += arr[j];
    return r;
}

long func_308(long a, long b) {
    long r = a + b * 48;
    for (int i = 0; i < 42; i++) r += (r >> 1) + 916;
    if (r > 767888) r = r % 1989;
    return r;
}

long func_309(long a, long b) {
    long r = a + b * 66;
    for (int i = 0; i < 15; i++) r += (r >> 1) + 251;
    return r;
}

long func_310(long a, long b) {
    long r = a + b * 20;
    for (int i = 0; i < 14; i++) r += (r >> 5) + 823;
    if (r > 786644) r = r % 6970;
    return r;
}

long func_311(long a, long b) {
    long r = a + b * 32;
    for (int i = 0; i < 50; i++) r += (r >> 3) + 846;
    for (int i = 0; i < 19; i++) r += (r >> 5) + 382;
    long arr[13];
    for (int j = 0; j < 13; j++) arr[j] = r + j;
    for (int j = 0; j < 13; j++) r += arr[j];
    return r;
}

long func_312(long a, long b) {
    long r = a + b * 23;
    for (int i = 0; i < 76; i++) r += (r >> 1) + 977;
    if (r > 929591) r = r % 7720;
    long arr[29];
    for (int j = 0; j < 29; j++) arr[j] = r + j;
    for (int j = 0; j < 29; j++) r += arr[j];
    return r;
}

long func_313(long a, long b) {
    long r = a + b * 42;
    for (int i = 0; i < 80; i++) r += (r >> 4) + 9;
    if (r > 315759) r = r % 9337;
    long arr[49];
    for (int j = 0; j < 49; j++) arr[j] = r + j;
    for (int j = 0; j < 49; j++) r += arr[j];
    return r;
}

long func_314(long a, long b) {
    long r = a + b * 32;
    for (int i = 0; i < 57; i++) r += (r >> 5) + 996;
    for (int i = 0; i < 73; i++) r += (r >> 2) + 751;
    if (r > 807423) r = r % 4116;
    return r;
}

long func_315(long a, long b) {
    long r = a + b * 53;
    for (int i = 0; i < 39; i++) r += (r >> 5) + 355;
    if (r > 737146) r = r % 257;
    long arr[10];
    for (int j = 0; j < 10; j++) arr[j] = r + j;
    for (int j = 0; j < 10; j++) r += arr[j];
    return r;
}

long func_316(long a, long b) {
    long r = a + b * 98;
    for (int i = 0; i < 58; i++) r += (r >> 3) + 107;
    for (int i = 0; i < 36; i++) r += (r >> 5) + 244;
    for (int i = 0; i < 63; i++) r += (r >> 4) + 985;
    long arr[27];
    for (int j = 0; j < 27; j++) arr[j] = r + j;
    for (int j = 0; j < 27; j++) r += arr[j];
    return r;
}

long func_317(long a, long b) {
    long r = a + b * 12;
    for (int i = 0; i < 39; i++) r += (r >> 5) + 423;
    if (r > 400586) r = r % 7611;
    long arr[15];
    for (int j = 0; j < 15; j++) arr[j] = r + j;
    for (int j = 0; j < 15; j++) r += arr[j];
    return r;
}

long func_318(long a, long b) {
    long r = a + b * 75;
    for (int i = 0; i < 74; i++) r += (r >> 2) + 653;
    if (r > 88465) r = r % 9797;
    long arr[37];
    for (int j = 0; j < 37; j++) arr[j] = r + j;
    for (int j = 0; j < 37; j++) r += arr[j];
    return r;
}

long func_319(long a, long b) {
    long r = a + b * 85;
    for (int i = 0; i < 40; i++) r += (r >> 3) + 268;
    if (r > 981025) r = r % 6538;
    long arr[30];
    for (int j = 0; j < 30; j++) arr[j] = r + j;
    for (int j = 0; j < 30; j++) r += arr[j];
    return r;
}

long func_320(long a, long b) {
    long r = a + b * 41;
    for (int i = 0; i < 44; i++) r += (r >> 2) + 77;
    for (int i = 0; i < 35; i++) r += (r >> 2) + 799;
    if (r > 124266) r = r % 2646;
    return r;
}

long func_321(long a, long b) {
    long r = a + b * 58;
    for (int i = 0; i < 50; i++) r += (r >> 4) + 124;
    for (int i = 0; i < 78; i++) r += (r >> 3) + 988;
    if (r > 483869) r = r % 5151;
    return r;
}

long func_322(long a, long b) {
    long r = a + b * 16;
    for (int i = 0; i < 30; i++) r += (r >> 3) + 847;
    if (r > 642608) r = r % 760;
    return r;
}

long func_323(long a, long b) {
    long r = a + b * 42;
    for (int i = 0; i < 21; i++) r += (r >> 2) + 992;
    if (r > 548401) r = r % 902;
    long arr[26];
    for (int j = 0; j < 26; j++) arr[j] = r + j;
    for (int j = 0; j < 26; j++) r += arr[j];
    return r;
}

long func_324(long a, long b) {
    long r = a + b * 23;
    for (int i = 0; i < 61; i++) r += (r >> 4) + 570;
    if (r > 271989) r = r % 1651;
    return r;
}

long func_325(long a, long b) {
    long r = a + b * 18;
    for (int i = 0; i < 11; i++) r += (r >> 1) + 851;
    if (r > 243086) r = r % 2241;
    return r;
}

long func_326(long a, long b) {
    long r = a + b * 52;
    for (int i = 0; i < 97; i++) r += (r >> 1) + 597;
    for (int i = 0; i < 85; i++) r += (r >> 3) + 940;
    if (r > 32859) r = r % 1156;
    return r;
}

long func_327(long a, long b) {
    long r = a + b * 83;
    for (int i = 0; i < 26; i++) r += (r >> 1) + 927;
    for (int i = 0; i < 52; i++) r += (r >> 1) + 44;
    if (r > 63097) r = r % 2852;
    long arr[37];
    for (int j = 0; j < 37; j++) arr[j] = r + j;
    for (int j = 0; j < 37; j++) r += arr[j];
    return r;
}

long func_328(long a, long b) {
    long r = a + b * 93;
    for (int i = 0; i < 73; i++) r += (r >> 1) + 392;
    for (int i = 0; i < 97; i++) r += (r >> 4) + 177;
    if (r > 962426) r = r % 3166;
    return r;
}

long func_329(long a, long b) {
    long r = a + b * 58;
    for (int i = 0; i < 14; i++) r += (r >> 5) + 635;
    if (r > 688720) r = r % 4935;
    return r;
}

long func_330(long a, long b) {
    long r = a + b * 71;
    for (int i = 0; i < 17; i++) r += (r >> 1) + 287;
    for (int i = 0; i < 59; i++) r += (r >> 2) + 430;
    long arr[43];
    for (int j = 0; j < 43; j++) arr[j] = r + j;
    for (int j = 0; j < 43; j++) r += arr[j];
    return r;
}

long func_331(long a, long b) {
    long r = a + b * 32;
    for (int i = 0; i < 79; i++) r += (r >> 1) + 392;
    for (int i = 0; i < 55; i++) r += (r >> 4) + 558;
    for (int i = 0; i < 72; i++) r += (r >> 3) + 935;
    if (r > 347226) r = r % 6463;
    return r;
}

long func_332(long a, long b) {
    long r = a + b * 4;
    for (int i = 0; i < 86; i++) r += (r >> 2) + 31;
    for (int i = 0; i < 45; i++) r += (r >> 1) + 829;
    if (r > 565149) r = r % 5956;
    long arr[24];
    for (int j = 0; j < 24; j++) arr[j] = r + j;
    for (int j = 0; j < 24; j++) r += arr[j];
    return r;
}

long func_333(long a, long b) {
    long r = a + b * 21;
    for (int i = 0; i < 41; i++) r += (r >> 2) + 273;
    if (r > 839672) r = r % 1016;
    long arr[24];
    for (int j = 0; j < 24; j++) arr[j] = r + j;
    for (int j = 0; j < 24; j++) r += arr[j];
    return r;
}

long func_334(long a, long b) {
    long r = a + b * 74;
    for (int i = 0; i < 55; i++) r += (r >> 2) + 181;
    for (int i = 0; i < 40; i++) r += (r >> 5) + 326;
    if (r > 741514) r = r % 5978;
    long arr[11];
    for (int j = 0; j < 11; j++) arr[j] = r + j;
    for (int j = 0; j < 11; j++) r += arr[j];
    return r;
}

long func_335(long a, long b) {
    long r = a + b * 91;
    for (int i = 0; i < 55; i++) r += (r >> 5) + 578;
    for (int i = 0; i < 28; i++) r += (r >> 5) + 972;
    for (int i = 0; i < 34; i++) r += (r >> 4) + 556;
    if (r > 524259) r = r % 721;
    return r;
}

long func_336(long a, long b) {
    long r = a + b * 30;
    for (int i = 0; i < 38; i++) r += (r >> 1) + 540;
    for (int i = 0; i < 71; i++) r += (r >> 1) + 340;
    for (int i = 0; i < 88; i++) r += (r >> 2) + 826;
    long arr[30];
    for (int j = 0; j < 30; j++) arr[j] = r + j;
    for (int j = 0; j < 30; j++) r += arr[j];
    return r;
}

long func_337(long a, long b) {
    long r = a + b * 8;
    for (int i = 0; i < 28; i++) r += (r >> 5) + 722;
    if (r > 821982) r = r % 1917;
    long arr[33];
    for (int j = 0; j < 33; j++) arr[j] = r + j;
    for (int j = 0; j < 33; j++) r += arr[j];
    return r;
}

long func_338(long a, long b) {
    long r = a + b * 10;
    for (int i = 0; i < 100; i++) r += (r >> 4) + 601;
    for (int i = 0; i < 22; i++) r += (r >> 3) + 310;
    if (r > 175154) r = r % 7257;
    long arr[41];
    for (int j = 0; j < 41; j++) arr[j] = r + j;
    for (int j = 0; j < 41; j++) r += arr[j];
    return r;
}

long func_339(long a, long b) {
    long r = a + b * 84;
    for (int i = 0; i < 32; i++) r += (r >> 5) + 711;
    for (int i = 0; i < 88; i++) r += (r >> 3) + 229;
    if (r > 864017) r = r % 2972;
    return r;
}

long func_340(long a, long b) {
    long r = a + b * 94;
    for (int i = 0; i < 47; i++) r += (r >> 2) + 182;
    for (int i = 0; i < 10; i++) r += (r >> 5) + 401;
    for (int i = 0; i < 82; i++) r += (r >> 1) + 187;
    if (r > 975778) r = r % 3719;
    long arr[16];
    for (int j = 0; j < 16; j++) arr[j] = r + j;
    for (int j = 0; j < 16; j++) r += arr[j];
    return r;
}

long func_341(long a, long b) {
    long r = a + b * 64;
    for (int i = 0; i < 52; i++) r += (r >> 1) + 244;
    if (r > 345039) r = r % 2850;
    long arr[15];
    for (int j = 0; j < 15; j++) arr[j] = r + j;
    for (int j = 0; j < 15; j++) r += arr[j];
    return r;
}

long func_342(long a, long b) {
    long r = a + b * 91;
    for (int i = 0; i < 91; i++) r += (r >> 3) + 458;
    for (int i = 0; i < 11; i++) r += (r >> 3) + 215;
    for (int i = 0; i < 41; i++) r += (r >> 1) + 359;
    return r;
}

long func_343(long a, long b) {
    long r = a + b * 1;
    for (int i = 0; i < 59; i++) r += (r >> 4) + 751;
    if (r > 184418) r = r % 6883;
    return r;
}

long func_344(long a, long b) {
    long r = a + b * 49;
    for (int i = 0; i < 79; i++) r += (r >> 4) + 104;
    for (int i = 0; i < 71; i++) r += (r >> 5) + 667;
    if (r > 246540) r = r % 2764;
    return r;
}

long func_345(long a, long b) {
    long r = a + b * 5;
    for (int i = 0; i < 12; i++) r += (r >> 3) + 268;
    for (int i = 0; i < 23; i++) r += (r >> 1) + 351;
    return r;
}

long func_346(long a, long b) {
    long r = a + b * 94;
    for (int i = 0; i < 80; i++) r += (r >> 1) + 347;
    if (r > 653453) r = r % 8009;
    long arr[37];
    for (int j = 0; j < 37; j++) arr[j] = r + j;
    for (int j = 0; j < 37; j++) r += arr[j];
    return r;
}

long func_347(long a, long b) {
    long r = a + b * 84;
    for (int i = 0; i < 87; i++) r += (r >> 4) + 161;
    return r;
}

long func_348(long a, long b) {
    long r = a + b * 25;
    for (int i = 0; i < 99; i++) r += (r >> 5) + 740;
    for (int i = 0; i < 79; i++) r += (r >> 3) + 677;
    return r;
}

long func_349(long a, long b) {
    long r = a + b * 7;
    for (int i = 0; i < 83; i++) r += (r >> 5) + 861;
    for (int i = 0; i < 72; i++) r += (r >> 2) + 56;
    if (r > 458377) r = r % 1535;
    return r;
}

long func_350(long a, long b) {
    long r = a + b * 85;
    for (int i = 0; i < 86; i++) r += (r >> 4) + 205;
    for (int i = 0; i < 22; i++) r += (r >> 1) + 212;
    for (int i = 0; i < 31; i++) r += (r >> 3) + 84;
    if (r > 131119) r = r % 5152;
    long arr[40];
    for (int j = 0; j < 40; j++) arr[j] = r + j;
    for (int j = 0; j < 40; j++) r += arr[j];
    return r;
}

long func_351(long a, long b) {
    long r = a + b * 63;
    for (int i = 0; i < 43; i++) r += (r >> 1) + 658;
    for (int i = 0; i < 79; i++) r += (r >> 4) + 190;
    for (int i = 0; i < 57; i++) r += (r >> 4) + 379;
    return r;
}

long func_352(long a, long b) {
    long r = a + b * 57;
    for (int i = 0; i < 43; i++) r += (r >> 2) + 858;
    for (int i = 0; i < 44; i++) r += (r >> 5) + 64;
    long arr[16];
    for (int j = 0; j < 16; j++) arr[j] = r + j;
    for (int j = 0; j < 16; j++) r += arr[j];
    return r;
}

long func_353(long a, long b) {
    long r = a + b * 11;
    for (int i = 0; i < 54; i++) r += (r >> 5) + 424;
    for (int i = 0; i < 85; i++) r += (r >> 2) + 567;
    for (int i = 0; i < 17; i++) r += (r >> 4) + 839;
    if (r > 571527) r = r % 7879;
    long arr[25];
    for (int j = 0; j < 25; j++) arr[j] = r + j;
    for (int j = 0; j < 25; j++) r += arr[j];
    return r;
}

long func_354(long a, long b) {
    long r = a + b * 61;
    for (int i = 0; i < 20; i++) r += (r >> 4) + 925;
    for (int i = 0; i < 14; i++) r += (r >> 5) + 585;
    if (r > 849333) r = r % 9463;
    long arr[49];
    for (int j = 0; j < 49; j++) arr[j] = r + j;
    for (int j = 0; j < 49; j++) r += arr[j];
    return r;
}

long func_355(long a, long b) {
    long r = a + b * 19;
    for (int i = 0; i < 67; i++) r += (r >> 2) + 972;
    if (r > 232182) r = r % 3257;
    return r;
}

long func_356(long a, long b) {
    long r = a + b * 55;
    for (int i = 0; i < 97; i++) r += (r >> 4) + 207;
    if (r > 667694) r = r % 2522;
    long arr[26];
    for (int j = 0; j < 26; j++) arr[j] = r + j;
    for (int j = 0; j < 26; j++) r += arr[j];
    return r;
}

long func_357(long a, long b) {
    long r = a + b * 41;
    for (int i = 0; i < 18; i++) r += (r >> 1) + 398;
    for (int i = 0; i < 81; i++) r += (r >> 4) + 566;
    for (int i = 0; i < 51; i++) r += (r >> 3) + 533;
    if (r > 925895) r = r % 302;
    long arr[49];
    for (int j = 0; j < 49; j++) arr[j] = r + j;
    for (int j = 0; j < 49; j++) r += arr[j];
    return r;
}

long func_358(long a, long b) {
    long r = a + b * 76;
    for (int i = 0; i < 63; i++) r += (r >> 1) + 425;
    for (int i = 0; i < 29; i++) r += (r >> 2) + 581;
    for (int i = 0; i < 85; i++) r += (r >> 5) + 777;
    if (r > 115071) r = r % 1830;
    long arr[16];
    for (int j = 0; j < 16; j++) arr[j] = r + j;
    for (int j = 0; j < 16; j++) r += arr[j];
    return r;
}

long func_359(long a, long b) {
    long r = a + b * 37;
    for (int i = 0; i < 54; i++) r += (r >> 4) + 271;
    for (int i = 0; i < 59; i++) r += (r >> 4) + 586;
    for (int i = 0; i < 87; i++) r += (r >> 4) + 39;
    return r;
}

long func_360(long a, long b) {
    long r = a + b * 80;
    for (int i = 0; i < 97; i++) r += (r >> 4) + 40;
    for (int i = 0; i < 60; i++) r += (r >> 3) + 708;
    for (int i = 0; i < 40; i++) r += (r >> 1) + 764;
    if (r > 291631) r = r % 6202;
    return r;
}

long func_361(long a, long b) {
    long r = a + b * 39;
    for (int i = 0; i < 45; i++) r += (r >> 4) + 879;
    for (int i = 0; i < 99; i++) r += (r >> 1) + 996;
    if (r > 150913) r = r % 5023;
    long arr[38];
    for (int j = 0; j < 38; j++) arr[j] = r + j;
    for (int j = 0; j < 38; j++) r += arr[j];
    return r;
}

long func_362(long a, long b) {
    long r = a + b * 42;
    for (int i = 0; i < 63; i++) r += (r >> 5) + 662;
    for (int i = 0; i < 21; i++) r += (r >> 2) + 453;
    long arr[41];
    for (int j = 0; j < 41; j++) arr[j] = r + j;
    for (int j = 0; j < 41; j++) r += arr[j];
    return r;
}

long func_363(long a, long b) {
    long r = a + b * 98;
    for (int i = 0; i < 57; i++) r += (r >> 1) + 528;
    for (int i = 0; i < 30; i++) r += (r >> 1) + 319;
    for (int i = 0; i < 100; i++) r += (r >> 5) + 414;
    long arr[46];
    for (int j = 0; j < 46; j++) arr[j] = r + j;
    for (int j = 0; j < 46; j++) r += arr[j];
    return r;
}

long func_364(long a, long b) {
    long r = a + b * 4;
    for (int i = 0; i < 34; i++) r += (r >> 2) + 858;
    return r;
}

long func_365(long a, long b) {
    long r = a + b * 7;
    for (int i = 0; i < 100; i++) r += (r >> 2) + 281;
    for (int i = 0; i < 57; i++) r += (r >> 4) + 518;
    if (r > 977912) r = r % 2129;
    long arr[25];
    for (int j = 0; j < 25; j++) arr[j] = r + j;
    for (int j = 0; j < 25; j++) r += arr[j];
    return r;
}

long func_366(long a, long b) {
    long r = a + b * 48;
    for (int i = 0; i < 86; i++) r += (r >> 4) + 182;
    for (int i = 0; i < 70; i++) r += (r >> 5) + 565;
    if (r > 181456) r = r % 4337;
    long arr[15];
    for (int j = 0; j < 15; j++) arr[j] = r + j;
    for (int j = 0; j < 15; j++) r += arr[j];
    return r;
}

long func_367(long a, long b) {
    long r = a + b * 37;
    for (int i = 0; i < 59; i++) r += (r >> 1) + 167;
    if (r > 827711) r = r % 3611;
    long arr[24];
    for (int j = 0; j < 24; j++) arr[j] = r + j;
    for (int j = 0; j < 24; j++) r += arr[j];
    return r;
}

long func_368(long a, long b) {
    long r = a + b * 87;
    for (int i = 0; i < 44; i++) r += (r >> 4) + 526;
    long arr[10];
    for (int j = 0; j < 10; j++) arr[j] = r + j;
    for (int j = 0; j < 10; j++) r += arr[j];
    return r;
}

long func_369(long a, long b) {
    long r = a + b * 61;
    for (int i = 0; i < 92; i++) r += (r >> 2) + 616;
    if (r > 244639) r = r % 4235;
    long arr[29];
    for (int j = 0; j < 29; j++) arr[j] = r + j;
    for (int j = 0; j < 29; j++) r += arr[j];
    return r;
}

long func_370(long a, long b) {
    long r = a + b * 92;
    for (int i = 0; i < 92; i++) r += (r >> 3) + 434;
    for (int i = 0; i < 58; i++) r += (r >> 3) + 471;
    for (int i = 0; i < 42; i++) r += (r >> 2) + 478;
    if (r > 555928) r = r % 6606;
    long arr[10];
    for (int j = 0; j < 10; j++) arr[j] = r + j;
    for (int j = 0; j < 10; j++) r += arr[j];
    return r;
}

long func_371(long a, long b) {
    long r = a + b * 66;
    for (int i = 0; i < 57; i++) r += (r >> 5) + 663;
    for (int i = 0; i < 86; i++) r += (r >> 5) + 290;
    for (int i = 0; i < 48; i++) r += (r >> 1) + 494;
    long arr[50];
    for (int j = 0; j < 50; j++) arr[j] = r + j;
    for (int j = 0; j < 50; j++) r += arr[j];
    return r;
}

long func_372(long a, long b) {
    long r = a + b * 42;
    for (int i = 0; i < 43; i++) r += (r >> 3) + 193;
    for (int i = 0; i < 29; i++) r += (r >> 5) + 784;
    return r;
}

long func_373(long a, long b) {
    long r = a + b * 77;
    for (int i = 0; i < 94; i++) r += (r >> 3) + 698;
    for (int i = 0; i < 27; i++) r += (r >> 1) + 672;
    if (r > 319963) r = r % 4350;
    long arr[35];
    for (int j = 0; j < 35; j++) arr[j] = r + j;
    for (int j = 0; j < 35; j++) r += arr[j];
    return r;
}

long func_374(long a, long b) {
    long r = a + b * 50;
    for (int i = 0; i < 14; i++) r += (r >> 5) + 726;
    for (int i = 0; i < 83; i++) r += (r >> 2) + 352;
    for (int i = 0; i < 38; i++) r += (r >> 5) + 654;
    if (r > 960561) r = r % 5973;
    long arr[20];
    for (int j = 0; j < 20; j++) arr[j] = r + j;
    for (int j = 0; j < 20; j++) r += arr[j];
    return r;
}

long func_375(long a, long b) {
    long r = a + b * 85;
    for (int i = 0; i < 33; i++) r += (r >> 3) + 100;
    for (int i = 0; i < 70; i++) r += (r >> 2) + 759;
    for (int i = 0; i < 43; i++) r += (r >> 5) + 782;
    if (r > 722730) r = r % 5599;
    long arr[24];
    for (int j = 0; j < 24; j++) arr[j] = r + j;
    for (int j = 0; j < 24; j++) r += arr[j];
    return r;
}

long func_376(long a, long b) {
    long r = a + b * 46;
    for (int i = 0; i < 49; i++) r += (r >> 4) + 808;
    if (r > 399737) r = r % 4369;
    long arr[39];
    for (int j = 0; j < 39; j++) arr[j] = r + j;
    for (int j = 0; j < 39; j++) r += arr[j];
    return r;
}

long func_377(long a, long b) {
    long r = a + b * 16;
    for (int i = 0; i < 16; i++) r += (r >> 5) + 595;
    for (int i = 0; i < 89; i++) r += (r >> 1) + 484;
    if (r > 534788) r = r % 2063;
    long arr[34];
    for (int j = 0; j < 34; j++) arr[j] = r + j;
    for (int j = 0; j < 34; j++) r += arr[j];
    return r;
}

long func_378(long a, long b) {
    long r = a + b * 68;
    for (int i = 0; i < 62; i++) r += (r >> 1) + 892;
    for (int i = 0; i < 29; i++) r += (r >> 2) + 206;
    if (r > 607062) r = r % 7596;
    return r;
}

long func_379(long a, long b) {
    long r = a + b * 92;
    for (int i = 0; i < 20; i++) r += (r >> 4) + 341;
    if (r > 195413) r = r % 5234;
    long arr[10];
    for (int j = 0; j < 10; j++) arr[j] = r + j;
    for (int j = 0; j < 10; j++) r += arr[j];
    return r;
}

long func_380(long a, long b) {
    long r = a + b * 58;
    for (int i = 0; i < 36; i++) r += (r >> 2) + 591;
    for (int i = 0; i < 30; i++) r += (r >> 4) + 805;
    if (r > 102318) r = r % 2220;
    long arr[50];
    for (int j = 0; j < 50; j++) arr[j] = r + j;
    for (int j = 0; j < 50; j++) r += arr[j];
    return r;
}

long func_381(long a, long b) {
    long r = a + b * 55;
    for (int i = 0; i < 64; i++) r += (r >> 4) + 393;
    for (int i = 0; i < 10; i++) r += (r >> 1) + 547;
    return r;
}

long func_382(long a, long b) {
    long r = a + b * 2;
    for (int i = 0; i < 77; i++) r += (r >> 2) + 19;
    for (int i = 0; i < 96; i++) r += (r >> 1) + 642;
    if (r > 247256) r = r % 5741;
    return r;
}

long func_383(long a, long b) {
    long r = a + b * 14;
    for (int i = 0; i < 74; i++) r += (r >> 5) + 314;
    for (int i = 0; i < 31; i++) r += (r >> 1) + 844;
    long arr[39];
    for (int j = 0; j < 39; j++) arr[j] = r + j;
    for (int j = 0; j < 39; j++) r += arr[j];
    return r;
}

long func_384(long a, long b) {
    long r = a + b * 94;
    for (int i = 0; i < 86; i++) r += (r >> 5) + 346;
    for (int i = 0; i < 65; i++) r += (r >> 2) + 351;
    for (int i = 0; i < 72; i++) r += (r >> 3) + 769;
    long arr[35];
    for (int j = 0; j < 35; j++) arr[j] = r + j;
    for (int j = 0; j < 35; j++) r += arr[j];
    return r;
}

long func_385(long a, long b) {
    long r = a + b * 3;
    for (int i = 0; i < 38; i++) r += (r >> 2) + 217;
    if (r > 628337) r = r % 8367;
    return r;
}

long func_386(long a, long b) {
    long r = a + b * 47;
    for (int i = 0; i < 93; i++) r += (r >> 1) + 385;
    for (int i = 0; i < 91; i++) r += (r >> 3) + 790;
    for (int i = 0; i < 78; i++) r += (r >> 5) + 50;
    if (r > 60290) r = r % 1871;
    long arr[11];
    for (int j = 0; j < 11; j++) arr[j] = r + j;
    for (int j = 0; j < 11; j++) r += arr[j];
    return r;
}

long func_387(long a, long b) {
    long r = a + b * 7;
    for (int i = 0; i < 24; i++) r += (r >> 4) + 455;
    for (int i = 0; i < 58; i++) r += (r >> 1) + 561;
    for (int i = 0; i < 42; i++) r += (r >> 4) + 719;
    long arr[50];
    for (int j = 0; j < 50; j++) arr[j] = r + j;
    for (int j = 0; j < 50; j++) r += arr[j];
    return r;
}

long func_388(long a, long b) {
    long r = a + b * 2;
    for (int i = 0; i < 63; i++) r += (r >> 1) + 679;
    for (int i = 0; i < 76; i++) r += (r >> 3) + 638;
    if (r > 153826) r = r % 6962;
    long arr[16];
    for (int j = 0; j < 16; j++) arr[j] = r + j;
    for (int j = 0; j < 16; j++) r += arr[j];
    return r;
}

long func_389(long a, long b) {
    long r = a + b * 66;
    for (int i = 0; i < 89; i++) r += (r >> 1) + 290;
    for (int i = 0; i < 24; i++) r += (r >> 1) + 510;
    for (int i = 0; i < 35; i++) r += (r >> 5) + 205;
    if (r > 881889) r = r % 8671;
    long arr[32];
    for (int j = 0; j < 32; j++) arr[j] = r + j;
    for (int j = 0; j < 32; j++) r += arr[j];
    return r;
}

long func_390(long a, long b) {
    long r = a + b * 91;
    for (int i = 0; i < 47; i++) r += (r >> 2) + 41;
    for (int i = 0; i < 80; i++) r += (r >> 4) + 933;
    long arr[31];
    for (int j = 0; j < 31; j++) arr[j] = r + j;
    for (int j = 0; j < 31; j++) r += arr[j];
    return r;
}

long func_391(long a, long b) {
    long r = a + b * 31;
    for (int i = 0; i < 11; i++) r += (r >> 1) + 929;
    long arr[41];
    for (int j = 0; j < 41; j++) arr[j] = r + j;
    for (int j = 0; j < 41; j++) r += arr[j];
    return r;
}

long func_392(long a, long b) {
    long r = a + b * 20;
    for (int i = 0; i < 75; i++) r += (r >> 1) + 741;
    if (r > 958729) r = r % 4292;
    long arr[39];
    for (int j = 0; j < 39; j++) arr[j] = r + j;
    for (int j = 0; j < 39; j++) r += arr[j];
    return r;
}

long func_393(long a, long b) {
    long r = a + b * 38;
    for (int i = 0; i < 69; i++) r += (r >> 1) + 103;
    for (int i = 0; i < 32; i++) r += (r >> 1) + 873;
    long arr[30];
    for (int j = 0; j < 30; j++) arr[j] = r + j;
    for (int j = 0; j < 30; j++) r += arr[j];
    return r;
}

long func_394(long a, long b) {
    long r = a + b * 55;
    for (int i = 0; i < 24; i++) r += (r >> 1) + 872;
    for (int i = 0; i < 15; i++) r += (r >> 1) + 873;
    for (int i = 0; i < 27; i++) r += (r >> 2) + 337;
    if (r > 468976) r = r % 4495;
    long arr[15];
    for (int j = 0; j < 15; j++) arr[j] = r + j;
    for (int j = 0; j < 15; j++) r += arr[j];
    return r;
}

long func_395(long a, long b) {
    long r = a + b * 48;
    for (int i = 0; i < 33; i++) r += (r >> 1) + 411;
    for (int i = 0; i < 61; i++) r += (r >> 4) + 279;
    if (r > 733415) r = r % 7935;
    long arr[20];
    for (int j = 0; j < 20; j++) arr[j] = r + j;
    for (int j = 0; j < 20; j++) r += arr[j];
    return r;
}

long func_396(long a, long b) {
    long r = a + b * 15;
    for (int i = 0; i < 99; i++) r += (r >> 1) + 966;
    if (r > 118751) r = r % 6916;
    long arr[40];
    for (int j = 0; j < 40; j++) arr[j] = r + j;
    for (int j = 0; j < 40; j++) r += arr[j];
    return r;
}

long func_397(long a, long b) {
    long r = a + b * 73;
    for (int i = 0; i < 66; i++) r += (r >> 2) + 626;
    for (int i = 0; i < 58; i++) r += (r >> 3) + 627;
    for (int i = 0; i < 13; i++) r += (r >> 2) + 495;
    if (r > 128423) r = r % 6838;
    return r;
}

long func_398(long a, long b) {
    long r = a + b * 9;
    for (int i = 0; i < 93; i++) r += (r >> 3) + 13;
    for (int i = 0; i < 100; i++) r += (r >> 5) + 786;
    if (r > 768931) r = r % 9357;
    return r;
}

long func_399(long a, long b) {
    long r = a + b * 86;
    for (int i = 0; i < 76; i++) r += (r >> 5) + 705;
    for (int i = 0; i < 99; i++) r += (r >> 5) + 98;
    if (r > 771949) r = r % 4172;
    return r;
}

long func_400(long a, long b) {
    long r = a + b * 85;
    for (int i = 0; i < 92; i++) r += (r >> 4) + 153;
    for (int i = 0; i < 81; i++) r += (r >> 5) + 56;
    for (int i = 0; i < 11; i++) r += (r >> 2) + 518;
    if (r > 903251) r = r % 8223;
    long arr[14];
    for (int j = 0; j < 14; j++) arr[j] = r + j;
    for (int j = 0; j < 14; j++) r += arr[j];
    return r;
}

long func_401(long a, long b) {
    long r = a + b * 97;
    for (int i = 0; i < 51; i++) r += (r >> 2) + 339;
    for (int i = 0; i < 45; i++) r += (r >> 1) + 520;
    long arr[35];
    for (int j = 0; j < 35; j++) arr[j] = r + j;
    for (int j = 0; j < 35; j++) r += arr[j];
    return r;
}

long func_402(long a, long b) {
    long r = a + b * 31;
    for (int i = 0; i < 68; i++) r += (r >> 4) + 821;
    if (r > 102295) r = r % 8266;
    return r;
}

long func_403(long a, long b) {
    long r = a + b * 16;
    for (int i = 0; i < 93; i++) r += (r >> 1) + 106;
    for (int i = 0; i < 61; i++) r += (r >> 4) + 37;
    if (r > 10177) r = r % 1589;
    long arr[49];
    for (int j = 0; j < 49; j++) arr[j] = r + j;
    for (int j = 0; j < 49; j++) r += arr[j];
    return r;
}

long func_404(long a, long b) {
    long r = a + b * 82;
    for (int i = 0; i < 75; i++) r += (r >> 5) + 212;
    for (int i = 0; i < 93; i++) r += (r >> 4) + 974;
    if (r > 875401) r = r % 989;
    long arr[39];
    for (int j = 0; j < 39; j++) arr[j] = r + j;
    for (int j = 0; j < 39; j++) r += arr[j];
    return r;
}

long func_405(long a, long b) {
    long r = a + b * 43;
    for (int i = 0; i < 89; i++) r += (r >> 5) + 485;
    for (int i = 0; i < 94; i++) r += (r >> 3) + 734;
    for (int i = 0; i < 67; i++) r += (r >> 1) + 100;
    if (r > 242518) r = r % 135;
    return r;
}

long func_406(long a, long b) {
    long r = a + b * 82;
    for (int i = 0; i < 80; i++) r += (r >> 5) + 383;
    for (int i = 0; i < 99; i++) r += (r >> 1) + 47;
    if (r > 526342) r = r % 2401;
    long arr[36];
    for (int j = 0; j < 36; j++) arr[j] = r + j;
    for (int j = 0; j < 36; j++) r += arr[j];
    return r;
}

long func_407(long a, long b) {
    long r = a + b * 14;
    for (int i = 0; i < 88; i++) r += (r >> 2) + 193;
    for (int i = 0; i < 25; i++) r += (r >> 4) + 221;
    if (r > 829378) r = r % 3222;
    long arr[16];
    for (int j = 0; j < 16; j++) arr[j] = r + j;
    for (int j = 0; j < 16; j++) r += arr[j];
    return r;
}

long func_408(long a, long b) {
    long r = a + b * 97;
    for (int i = 0; i < 15; i++) r += (r >> 5) + 127;
    for (int i = 0; i < 67; i++) r += (r >> 4) + 675;
    if (r > 538689) r = r % 2305;
    long arr[10];
    for (int j = 0; j < 10; j++) arr[j] = r + j;
    for (int j = 0; j < 10; j++) r += arr[j];
    return r;
}

long func_409(long a, long b) {
    long r = a + b * 68;
    for (int i = 0; i < 16; i++) r += (r >> 5) + 958;
    for (int i = 0; i < 65; i++) r += (r >> 5) + 495;
    for (int i = 0; i < 75; i++) r += (r >> 2) + 709;
    if (r > 775979) r = r % 2203;
    return r;
}

long func_410(long a, long b) {
    long r = a + b * 85;
    for (int i = 0; i < 87; i++) r += (r >> 3) + 517;
    for (int i = 0; i < 59; i++) r += (r >> 4) + 624;
    for (int i = 0; i < 98; i++) r += (r >> 2) + 281;
    if (r > 369513) r = r % 4919;
    return r;
}

long func_411(long a, long b) {
    long r = a + b * 18;
    for (int i = 0; i < 62; i++) r += (r >> 5) + 717;
    if (r > 547179) r = r % 4997;
    long arr[45];
    for (int j = 0; j < 45; j++) arr[j] = r + j;
    for (int j = 0; j < 45; j++) r += arr[j];
    return r;
}

long func_412(long a, long b) {
    long r = a + b * 41;
    for (int i = 0; i < 80; i++) r += (r >> 2) + 206;
    for (int i = 0; i < 36; i++) r += (r >> 5) + 732;
    for (int i = 0; i < 47; i++) r += (r >> 3) + 944;
    if (r > 754904) r = r % 3013;
    long arr[50];
    for (int j = 0; j < 50; j++) arr[j] = r + j;
    for (int j = 0; j < 50; j++) r += arr[j];
    return r;
}

long func_413(long a, long b) {
    long r = a + b * 42;
    for (int i = 0; i < 24; i++) r += (r >> 3) + 576;
    for (int i = 0; i < 71; i++) r += (r >> 5) + 585;
    for (int i = 0; i < 95; i++) r += (r >> 4) + 691;
    if (r > 892260) r = r % 8847;
    return r;
}

long func_414(long a, long b) {
    long r = a + b * 55;
    for (int i = 0; i < 76; i++) r += (r >> 1) + 26;
    if (r > 65642) r = r % 1027;
    return r;
}

long func_415(long a, long b) {
    long r = a + b * 97;
    for (int i = 0; i < 46; i++) r += (r >> 3) + 150;
    if (r > 734141) r = r % 4935;
    return r;
}

long func_416(long a, long b) {
    long r = a + b * 70;
    for (int i = 0; i < 55; i++) r += (r >> 4) + 105;
    if (r > 718340) r = r % 9305;
    long arr[45];
    for (int j = 0; j < 45; j++) arr[j] = r + j;
    for (int j = 0; j < 45; j++) r += arr[j];
    return r;
}

long func_417(long a, long b) {
    long r = a + b * 50;
    for (int i = 0; i < 75; i++) r += (r >> 3) + 710;
    if (r > 981489) r = r % 6351;
    return r;
}

long func_418(long a, long b) {
    long r = a + b * 88;
    for (int i = 0; i < 80; i++) r += (r >> 1) + 14;
    for (int i = 0; i < 42; i++) r += (r >> 2) + 636;
    if (r > 912241) r = r % 7359;
    long arr[50];
    for (int j = 0; j < 50; j++) arr[j] = r + j;
    for (int j = 0; j < 50; j++) r += arr[j];
    return r;
}

long func_419(long a, long b) {
    long r = a + b * 91;
    for (int i = 0; i < 92; i++) r += (r >> 3) + 774;
    for (int i = 0; i < 85; i++) r += (r >> 5) + 757;
    for (int i = 0; i < 87; i++) r += (r >> 2) + 795;
    if (r > 212897) r = r % 4919;
    return r;
}

long func_420(long a, long b) {
    long r = a + b * 88;
    for (int i = 0; i < 33; i++) r += (r >> 2) + 753;
    if (r > 405521) r = r % 765;
    return r;
}

long func_421(long a, long b) {
    long r = a + b * 72;
    for (int i = 0; i < 26; i++) r += (r >> 2) + 599;
    for (int i = 0; i < 42; i++) r += (r >> 1) + 339;
    if (r > 993034) r = r % 2636;
    return r;
}

long func_422(long a, long b) {
    long r = a + b * 42;
    for (int i = 0; i < 16; i++) r += (r >> 5) + 864;
    for (int i = 0; i < 94; i++) r += (r >> 3) + 503;
    for (int i = 0; i < 83; i++) r += (r >> 5) + 367;
    long arr[43];
    for (int j = 0; j < 43; j++) arr[j] = r + j;
    for (int j = 0; j < 43; j++) r += arr[j];
    return r;
}

long func_423(long a, long b) {
    long r = a + b * 29;
    for (int i = 0; i < 76; i++) r += (r >> 1) + 806;
    if (r > 446135) r = r % 8997;
    long arr[15];
    for (int j = 0; j < 15; j++) arr[j] = r + j;
    for (int j = 0; j < 15; j++) r += arr[j];
    return r;
}

long func_424(long a, long b) {
    long r = a + b * 45;
    for (int i = 0; i < 37; i++) r += (r >> 3) + 340;
    if (r > 239056) r = r % 8791;
    return r;
}

long func_425(long a, long b) {
    long r = a + b * 72;
    for (int i = 0; i < 11; i++) r += (r >> 1) + 685;
    for (int i = 0; i < 54; i++) r += (r >> 4) + 247;
    for (int i = 0; i < 92; i++) r += (r >> 5) + 941;
    if (r > 51814) r = r % 5358;
    return r;
}

long func_426(long a, long b) {
    long r = a + b * 15;
    for (int i = 0; i < 42; i++) r += (r >> 5) + 742;
    for (int i = 0; i < 46; i++) r += (r >> 1) + 934;
    if (r > 817921) r = r % 6243;
    long arr[42];
    for (int j = 0; j < 42; j++) arr[j] = r + j;
    for (int j = 0; j < 42; j++) r += arr[j];
    return r;
}

long func_427(long a, long b) {
    long r = a + b * 58;
    for (int i = 0; i < 15; i++) r += (r >> 3) + 920;
    for (int i = 0; i < 93; i++) r += (r >> 2) + 329;
    if (r > 110617) r = r % 2842;
    long arr[44];
    for (int j = 0; j < 44; j++) arr[j] = r + j;
    for (int j = 0; j < 44; j++) r += arr[j];
    return r;
}

long func_428(long a, long b) {
    long r = a + b * 69;
    for (int i = 0; i < 90; i++) r += (r >> 1) + 216;
    if (r > 821159) r = r % 3592;
    long arr[37];
    for (int j = 0; j < 37; j++) arr[j] = r + j;
    for (int j = 0; j < 37; j++) r += arr[j];
    return r;
}

long func_429(long a, long b) {
    long r = a + b * 14;
    for (int i = 0; i < 78; i++) r += (r >> 4) + 663;
    if (r > 85623) r = r % 2619;
    return r;
}

long func_430(long a, long b) {
    long r = a + b * 92;
    for (int i = 0; i < 14; i++) r += (r >> 1) + 76;
    for (int i = 0; i < 16; i++) r += (r >> 2) + 814;
    return r;
}

long func_431(long a, long b) {
    long r = a + b * 30;
    for (int i = 0; i < 62; i++) r += (r >> 4) + 462;
    for (int i = 0; i < 90; i++) r += (r >> 4) + 444;
    if (r > 418422) r = r % 2038;
    long arr[49];
    for (int j = 0; j < 49; j++) arr[j] = r + j;
    for (int j = 0; j < 49; j++) r += arr[j];
    return r;
}

long func_432(long a, long b) {
    long r = a + b * 9;
    for (int i = 0; i < 84; i++) r += (r >> 1) + 718;
    for (int i = 0; i < 19; i++) r += (r >> 3) + 951;
    for (int i = 0; i < 74; i++) r += (r >> 1) + 297;
    if (r > 325989) r = r % 1517;
    return r;
}

long func_433(long a, long b) {
    long r = a + b * 57;
    for (int i = 0; i < 60; i++) r += (r >> 1) + 486;
    for (int i = 0; i < 30; i++) r += (r >> 5) + 226;
    return r;
}

long func_434(long a, long b) {
    long r = a + b * 70;
    for (int i = 0; i < 91; i++) r += (r >> 2) + 306;
    for (int i = 0; i < 96; i++) r += (r >> 3) + 981;
    if (r > 590412) r = r % 9194;
    return r;
}

long func_435(long a, long b) {
    long r = a + b * 6;
    for (int i = 0; i < 83; i++) r += (r >> 5) + 404;
    if (r > 99261) r = r % 5092;
    return r;
}

long func_436(long a, long b) {
    long r = a + b * 95;
    for (int i = 0; i < 54; i++) r += (r >> 2) + 423;
    for (int i = 0; i < 92; i++) r += (r >> 5) + 146;
    for (int i = 0; i < 30; i++) r += (r >> 2) + 227;
    if (r > 275018) r = r % 3283;
    return r;
}

long func_437(long a, long b) {
    long r = a + b * 86;
    for (int i = 0; i < 16; i++) r += (r >> 5) + 473;
    for (int i = 0; i < 92; i++) r += (r >> 5) + 75;
    for (int i = 0; i < 47; i++) r += (r >> 1) + 257;
    long arr[41];
    for (int j = 0; j < 41; j++) arr[j] = r + j;
    for (int j = 0; j < 41; j++) r += arr[j];
    return r;
}

long func_438(long a, long b) {
    long r = a + b * 43;
    for (int i = 0; i < 26; i++) r += (r >> 2) + 103;
    for (int i = 0; i < 46; i++) r += (r >> 5) + 72;
    if (r > 343222) r = r % 8060;
    return r;
}

long func_439(long a, long b) {
    long r = a + b * 79;
    for (int i = 0; i < 49; i++) r += (r >> 5) + 157;
    for (int i = 0; i < 82; i++) r += (r >> 5) + 374;
    for (int i = 0; i < 50; i++) r += (r >> 4) + 173;
    return r;
}

long func_440(long a, long b) {
    long r = a + b * 29;
    for (int i = 0; i < 92; i++) r += (r >> 4) + 284;
    for (int i = 0; i < 56; i++) r += (r >> 2) + 696;
    for (int i = 0; i < 52; i++) r += (r >> 4) + 474;
    if (r > 822402) r = r % 5104;
    return r;
}

long func_441(long a, long b) {
    long r = a + b * 14;
    for (int i = 0; i < 92; i++) r += (r >> 5) + 84;
    if (r > 910426) r = r % 2393;
    long arr[22];
    for (int j = 0; j < 22; j++) arr[j] = r + j;
    for (int j = 0; j < 22; j++) r += arr[j];
    return r;
}

long func_442(long a, long b) {
    long r = a + b * 34;
    for (int i = 0; i < 90; i++) r += (r >> 1) + 745;
    for (int i = 0; i < 19; i++) r += (r >> 1) + 870;
    for (int i = 0; i < 74; i++) r += (r >> 1) + 833;
    if (r > 434814) r = r % 9767;
    return r;
}

long func_443(long a, long b) {
    long r = a + b * 5;
    for (int i = 0; i < 43; i++) r += (r >> 5) + 916;
    for (int i = 0; i < 79; i++) r += (r >> 4) + 670;
    for (int i = 0; i < 29; i++) r += (r >> 3) + 402;
    long arr[28];
    for (int j = 0; j < 28; j++) arr[j] = r + j;
    for (int j = 0; j < 28; j++) r += arr[j];
    return r;
}

long func_444(long a, long b) {
    long r = a + b * 18;
    for (int i = 0; i < 74; i++) r += (r >> 5) + 93;
    for (int i = 0; i < 60; i++) r += (r >> 3) + 515;
    return r;
}

long func_445(long a, long b) {
    long r = a + b * 79;
    for (int i = 0; i < 31; i++) r += (r >> 5) + 144;
    for (int i = 0; i < 67; i++) r += (r >> 2) + 184;
    for (int i = 0; i < 82; i++) r += (r >> 5) + 676;
    if (r > 163300) r = r % 8021;
    long arr[12];
    for (int j = 0; j < 12; j++) arr[j] = r + j;
    for (int j = 0; j < 12; j++) r += arr[j];
    return r;
}

long func_446(long a, long b) {
    long r = a + b * 29;
    for (int i = 0; i < 39; i++) r += (r >> 1) + 271;
    for (int i = 0; i < 57; i++) r += (r >> 2) + 44;
    if (r > 553042) r = r % 6018;
    return r;
}

long func_447(long a, long b) {
    long r = a + b * 59;
    for (int i = 0; i < 15; i++) r += (r >> 3) + 106;
    if (r > 556699) r = r % 4580;
    long arr[26];
    for (int j = 0; j < 26; j++) arr[j] = r + j;
    for (int j = 0; j < 26; j++) r += arr[j];
    return r;
}

long func_448(long a, long b) {
    long r = a + b * 75;
    for (int i = 0; i < 82; i++) r += (r >> 2) + 386;
    for (int i = 0; i < 93; i++) r += (r >> 4) + 375;
    for (int i = 0; i < 85; i++) r += (r >> 1) + 530;
    long arr[24];
    for (int j = 0; j < 24; j++) arr[j] = r + j;
    for (int j = 0; j < 24; j++) r += arr[j];
    return r;
}

long func_449(long a, long b) {
    long r = a + b * 67;
    for (int i = 0; i < 55; i++) r += (r >> 3) + 499;
    for (int i = 0; i < 71; i++) r += (r >> 5) + 7;
    if (r > 155718) r = r % 7307;
    return r;
}

long func_450(long a, long b) {
    long r = a + b * 10;
    for (int i = 0; i < 92; i++) r += (r >> 3) + 217;
    for (int i = 0; i < 29; i++) r += (r >> 2) + 162;
    for (int i = 0; i < 56; i++) r += (r >> 5) + 735;
    if (r > 703223) r = r % 3873;
    return r;
}

long func_451(long a, long b) {
    long r = a + b * 43;
    for (int i = 0; i < 24; i++) r += (r >> 4) + 692;
    for (int i = 0; i < 71; i++) r += (r >> 4) + 216;
    for (int i = 0; i < 85; i++) r += (r >> 2) + 663;
    if (r > 33536) r = r % 4092;
    return r;
}

long func_452(long a, long b) {
    long r = a + b * 74;
    for (int i = 0; i < 30; i++) r += (r >> 2) + 645;
    for (int i = 0; i < 75; i++) r += (r >> 1) + 913;
    for (int i = 0; i < 83; i++) r += (r >> 2) + 58;
    long arr[43];
    for (int j = 0; j < 43; j++) arr[j] = r + j;
    for (int j = 0; j < 43; j++) r += arr[j];
    return r;
}

long func_453(long a, long b) {
    long r = a + b * 52;
    for (int i = 0; i < 82; i++) r += (r >> 1) + 900;
    for (int i = 0; i < 94; i++) r += (r >> 3) + 970;
    for (int i = 0; i < 20; i++) r += (r >> 2) + 460;
    if (r > 504312) r = r % 7991;
    return r;
}

long func_454(long a, long b) {
    long r = a + b * 53;
    for (int i = 0; i < 28; i++) r += (r >> 5) + 841;
    for (int i = 0; i < 33; i++) r += (r >> 5) + 676;
    for (int i = 0; i < 75; i++) r += (r >> 3) + 172;
    if (r > 369316) r = r % 7529;
    long arr[14];
    for (int j = 0; j < 14; j++) arr[j] = r + j;
    for (int j = 0; j < 14; j++) r += arr[j];
    return r;
}

long func_455(long a, long b) {
    long r = a + b * 30;
    for (int i = 0; i < 59; i++) r += (r >> 2) + 112;
    for (int i = 0; i < 12; i++) r += (r >> 2) + 536;
    if (r > 538859) r = r % 6977;
    long arr[48];
    for (int j = 0; j < 48; j++) arr[j] = r + j;
    for (int j = 0; j < 48; j++) r += arr[j];
    return r;
}

long func_456(long a, long b) {
    long r = a + b * 13;
    for (int i = 0; i < 70; i++) r += (r >> 5) + 615;
    long arr[42];
    for (int j = 0; j < 42; j++) arr[j] = r + j;
    for (int j = 0; j < 42; j++) r += arr[j];
    return r;
}

long func_457(long a, long b) {
    long r = a + b * 97;
    for (int i = 0; i < 21; i++) r += (r >> 4) + 676;
    long arr[10];
    for (int j = 0; j < 10; j++) arr[j] = r + j;
    for (int j = 0; j < 10; j++) r += arr[j];
    return r;
}

long func_458(long a, long b) {
    long r = a + b * 87;
    for (int i = 0; i < 65; i++) r += (r >> 5) + 431;
    for (int i = 0; i < 57; i++) r += (r >> 1) + 715;
    for (int i = 0; i < 77; i++) r += (r >> 4) + 235;
    if (r > 515543) r = r % 6346;
    return r;
}

long func_459(long a, long b) {
    long r = a + b * 95;
    for (int i = 0; i < 83; i++) r += (r >> 1) + 436;
    for (int i = 0; i < 27; i++) r += (r >> 3) + 489;
    for (int i = 0; i < 39; i++) r += (r >> 1) + 291;
    if (r > 580143) r = r % 6795;
    return r;
}

long func_460(long a, long b) {
    long r = a + b * 1;
    for (int i = 0; i < 10; i++) r += (r >> 5) + 536;
    for (int i = 0; i < 25; i++) r += (r >> 5) + 8;
    for (int i = 0; i < 58; i++) r += (r >> 2) + 705;
    if (r > 438705) r = r % 6035;
    return r;
}

long func_461(long a, long b) {
    long r = a + b * 55;
    for (int i = 0; i < 84; i++) r += (r >> 3) + 268;
    for (int i = 0; i < 78; i++) r += (r >> 4) + 579;
    for (int i = 0; i < 56; i++) r += (r >> 5) + 283;
    if (r > 426760) r = r % 3437;
    return r;
}

long func_462(long a, long b) {
    long r = a + b * 72;
    for (int i = 0; i < 32; i++) r += (r >> 3) + 573;
    for (int i = 0; i < 81; i++) r += (r >> 4) + 260;
    if (r > 615711) r = r % 5741;
    long arr[35];
    for (int j = 0; j < 35; j++) arr[j] = r + j;
    for (int j = 0; j < 35; j++) r += arr[j];
    return r;
}

long func_463(long a, long b) {
    long r = a + b * 95;
    for (int i = 0; i < 94; i++) r += (r >> 1) + 766;
    long arr[20];
    for (int j = 0; j < 20; j++) arr[j] = r + j;
    for (int j = 0; j < 20; j++) r += arr[j];
    return r;
}

long func_464(long a, long b) {
    long r = a + b * 13;
    for (int i = 0; i < 75; i++) r += (r >> 4) + 805;
    if (r > 587321) r = r % 952;
    return r;
}

long func_465(long a, long b) {
    long r = a + b * 82;
    for (int i = 0; i < 21; i++) r += (r >> 2) + 483;
    if (r > 466526) r = r % 1544;
    return r;
}

long func_466(long a, long b) {
    long r = a + b * 29;
    for (int i = 0; i < 20; i++) r += (r >> 5) + 39;
    for (int i = 0; i < 59; i++) r += (r >> 4) + 629;
    if (r > 310384) r = r % 9888;
    return r;
}

long func_467(long a, long b) {
    long r = a + b * 23;
    for (int i = 0; i < 73; i++) r += (r >> 4) + 11;
    for (int i = 0; i < 35; i++) r += (r >> 5) + 293;
    for (int i = 0; i < 34; i++) r += (r >> 1) + 803;
    if (r > 550869) r = r % 3895;
    long arr[12];
    for (int j = 0; j < 12; j++) arr[j] = r + j;
    for (int j = 0; j < 12; j++) r += arr[j];
    return r;
}

long func_468(long a, long b) {
    long r = a + b * 47;
    for (int i = 0; i < 93; i++) r += (r >> 1) + 162;
    return r;
}

long func_469(long a, long b) {
    long r = a + b * 52;
    for (int i = 0; i < 95; i++) r += (r >> 4) + 416;
    for (int i = 0; i < 85; i++) r += (r >> 2) + 531;
    long arr[15];
    for (int j = 0; j < 15; j++) arr[j] = r + j;
    for (int j = 0; j < 15; j++) r += arr[j];
    return r;
}

long func_470(long a, long b) {
    long r = a + b * 71;
    for (int i = 0; i < 81; i++) r += (r >> 5) + 357;
    for (int i = 0; i < 54; i++) r += (r >> 3) + 232;
    if (r > 213974) r = r % 7550;
    long arr[46];
    for (int j = 0; j < 46; j++) arr[j] = r + j;
    for (int j = 0; j < 46; j++) r += arr[j];
    return r;
}

long func_471(long a, long b) {
    long r = a + b * 1;
    for (int i = 0; i < 32; i++) r += (r >> 4) + 519;
    for (int i = 0; i < 23; i++) r += (r >> 5) + 75;
    if (r > 366480) r = r % 2017;
    long arr[26];
    for (int j = 0; j < 26; j++) arr[j] = r + j;
    for (int j = 0; j < 26; j++) r += arr[j];
    return r;
}

long func_472(long a, long b) {
    long r = a + b * 69;
    for (int i = 0; i < 42; i++) r += (r >> 4) + 990;
    for (int i = 0; i < 58; i++) r += (r >> 5) + 496;
    for (int i = 0; i < 41; i++) r += (r >> 3) + 985;
    if (r > 724703) r = r % 7648;
    long arr[11];
    for (int j = 0; j < 11; j++) arr[j] = r + j;
    for (int j = 0; j < 11; j++) r += arr[j];
    return r;
}

long func_473(long a, long b) {
    long r = a + b * 62;
    for (int i = 0; i < 43; i++) r += (r >> 1) + 392;
    if (r > 241087) r = r % 3867;
    long arr[36];
    for (int j = 0; j < 36; j++) arr[j] = r + j;
    for (int j = 0; j < 36; j++) r += arr[j];
    return r;
}

long func_474(long a, long b) {
    long r = a + b * 46;
    for (int i = 0; i < 78; i++) r += (r >> 1) + 718;
    for (int i = 0; i < 43; i++) r += (r >> 2) + 295;
    for (int i = 0; i < 21; i++) r += (r >> 4) + 690;
    if (r > 368605) r = r % 1345;
    long arr[21];
    for (int j = 0; j < 21; j++) arr[j] = r + j;
    for (int j = 0; j < 21; j++) r += arr[j];
    return r;
}

long func_475(long a, long b) {
    long r = a + b * 61;
    for (int i = 0; i < 55; i++) r += (r >> 2) + 916;
    for (int i = 0; i < 83; i++) r += (r >> 3) + 188;
    if (r > 726289) r = r % 3215;
    return r;
}

long func_476(long a, long b) {
    long r = a + b * 26;
    for (int i = 0; i < 40; i++) r += (r >> 3) + 212;
    long arr[49];
    for (int j = 0; j < 49; j++) arr[j] = r + j;
    for (int j = 0; j < 49; j++) r += arr[j];
    return r;
}

long func_477(long a, long b) {
    long r = a + b * 46;
    for (int i = 0; i < 23; i++) r += (r >> 1) + 943;
    long arr[41];
    for (int j = 0; j < 41; j++) arr[j] = r + j;
    for (int j = 0; j < 41; j++) r += arr[j];
    return r;
}

long func_478(long a, long b) {
    long r = a + b * 79;
    for (int i = 0; i < 79; i++) r += (r >> 1) + 869;
    if (r > 660817) r = r % 5267;
    return r;
}

long func_479(long a, long b) {
    long r = a + b * 74;
    for (int i = 0; i < 72; i++) r += (r >> 2) + 783;
    for (int i = 0; i < 75; i++) r += (r >> 3) + 408;
    long arr[13];
    for (int j = 0; j < 13; j++) arr[j] = r + j;
    for (int j = 0; j < 13; j++) r += arr[j];
    return r;
}

long func_480(long a, long b) {
    long r = a + b * 68;
    for (int i = 0; i < 71; i++) r += (r >> 5) + 34;
    for (int i = 0; i < 74; i++) r += (r >> 3) + 404;
    if (r > 823594) r = r % 2963;
    return r;
}

long func_481(long a, long b) {
    long r = a + b * 16;
    for (int i = 0; i < 76; i++) r += (r >> 4) + 324;
    for (int i = 0; i < 98; i++) r += (r >> 1) + 13;
    for (int i = 0; i < 96; i++) r += (r >> 2) + 389;
    if (r > 351244) r = r % 6024;
    long arr[26];
    for (int j = 0; j < 26; j++) arr[j] = r + j;
    for (int j = 0; j < 26; j++) r += arr[j];
    return r;
}

long func_482(long a, long b) {
    long r = a + b * 24;
    for (int i = 0; i < 43; i++) r += (r >> 2) + 276;
    for (int i = 0; i < 70; i++) r += (r >> 5) + 352;
    for (int i = 0; i < 56; i++) r += (r >> 2) + 511;
    if (r > 449450) r = r % 6199;
    return r;
}

long func_483(long a, long b) {
    long r = a + b * 52;
    for (int i = 0; i < 67; i++) r += (r >> 2) + 586;
    for (int i = 0; i < 26; i++) r += (r >> 5) + 703;
    return r;
}

long func_484(long a, long b) {
    long r = a + b * 35;
    for (int i = 0; i < 81; i++) r += (r >> 4) + 877;
    if (r > 162928) r = r % 2550;
    return r;
}

long func_485(long a, long b) {
    long r = a + b * 2;
    for (int i = 0; i < 63; i++) r += (r >> 4) + 138;
    if (r > 900649) r = r % 8570;
    long arr[30];
    for (int j = 0; j < 30; j++) arr[j] = r + j;
    for (int j = 0; j < 30; j++) r += arr[j];
    return r;
}

long func_486(long a, long b) {
    long r = a + b * 63;
    for (int i = 0; i < 42; i++) r += (r >> 5) + 880;
    for (int i = 0; i < 82; i++) r += (r >> 1) + 408;
    return r;
}

long func_487(long a, long b) {
    long r = a + b * 28;
    for (int i = 0; i < 70; i++) r += (r >> 1) + 461;
    for (int i = 0; i < 52; i++) r += (r >> 3) + 370;
    if (r > 594572) r = r % 4322;
    return r;
}

long func_488(long a, long b) {
    long r = a + b * 53;
    for (int i = 0; i < 54; i++) r += (r >> 5) + 204;
    if (r > 691433) r = r % 8921;
    return r;
}

long func_489(long a, long b) {
    long r = a + b * 37;
    for (int i = 0; i < 51; i++) r += (r >> 5) + 500;
    for (int i = 0; i < 67; i++) r += (r >> 1) + 391;
    if (r > 496279) r = r % 2473;
    long arr[50];
    for (int j = 0; j < 50; j++) arr[j] = r + j;
    for (int j = 0; j < 50; j++) r += arr[j];
    return r;
}

long func_490(long a, long b) {
    long r = a + b * 44;
    for (int i = 0; i < 90; i++) r += (r >> 5) + 586;
    for (int i = 0; i < 61; i++) r += (r >> 1) + 82;
    return r;
}

long func_491(long a, long b) {
    long r = a + b * 41;
    for (int i = 0; i < 47; i++) r += (r >> 3) + 620;
    for (int i = 0; i < 92; i++) r += (r >> 4) + 278;
    for (int i = 0; i < 66; i++) r += (r >> 3) + 766;
    if (r > 482161) r = r % 6882;
    return r;
}

long func_492(long a, long b) {
    long r = a + b * 3;
    for (int i = 0; i < 40; i++) r += (r >> 3) + 964;
    if (r > 796159) r = r % 1411;
    return r;
}

long func_493(long a, long b) {
    long r = a + b * 51;
    for (int i = 0; i < 22; i++) r += (r >> 1) + 960;
    if (r > 585074) r = r % 981;
    return r;
}

long func_494(long a, long b) {
    long r = a + b * 51;
    for (int i = 0; i < 20; i++) r += (r >> 1) + 269;
    for (int i = 0; i < 89; i++) r += (r >> 2) + 87;
    for (int i = 0; i < 93; i++) r += (r >> 4) + 317;
    long arr[38];
    for (int j = 0; j < 38; j++) arr[j] = r + j;
    for (int j = 0; j < 38; j++) r += arr[j];
    return r;
}

long func_495(long a, long b) {
    long r = a + b * 81;
    for (int i = 0; i < 26; i++) r += (r >> 5) + 859;
    return r;
}

long func_496(long a, long b) {
    long r = a + b * 46;
    for (int i = 0; i < 70; i++) r += (r >> 4) + 999;
    for (int i = 0; i < 79; i++) r += (r >> 3) + 562;
    if (r > 741510) r = r % 8935;
    return r;
}

long func_497(long a, long b) {
    long r = a + b * 77;
    for (int i = 0; i < 90; i++) r += (r >> 5) + 446;
    for (int i = 0; i < 77; i++) r += (r >> 5) + 318;
    if (r > 515048) r = r % 8941;
    return r;
}

long func_498(long a, long b) {
    long r = a + b * 12;
    for (int i = 0; i < 49; i++) r += (r >> 3) + 423;
    for (int i = 0; i < 43; i++) r += (r >> 2) + 311;
    long arr[18];
    for (int j = 0; j < 18; j++) arr[j] = r + j;
    for (int j = 0; j < 18; j++) r += arr[j];
    return r;
}

long func_499(long a, long b) {
    long r = a + b * 45;
    for (int i = 0; i < 70; i++) r += (r >> 5) + 9;
    for (int i = 0; i < 98; i++) r += (r >> 4) + 970;
    if (r > 324164) r = r % 249;
    long arr[28];
    for (int j = 0; j < 28; j++) arr[j] = r + j;
    for (int j = 0; j < 28; j++) r += arr[j];
    return r;
}

int main(void) {
    long total = 0;
    total += func_0(77L, 30L);
    total += func_1(1L, 71L);
    total += func_2(48L, 25L);
    total += func_3(53L, 72L);
    total += func_4(56L, 51L);
    total += func_5(32L, 21L);
    total += func_6(92L, 95L);
    total += func_7(83L, 50L);
    total += func_8(49L, 29L);
    total += func_9(34L, 11L);
    total += func_10(55L, 81L);
    total += func_11(31L, 67L);
    total += func_12(98L, 79L);
    total += func_13(89L, 88L);
    total += func_14(35L, 37L);
    total += func_15(84L, 96L);
    total += func_16(69L, 35L);
    total += func_17(53L, 25L);
    total += func_18(9L, 24L);
    total += func_19(18L, 38L);
    total += func_20(15L, 82L);
    total += func_21(59L, 80L);
    total += func_22(58L, 35L);
    total += func_23(90L, 80L);
    total += func_24(63L, 25L);
    total += func_25(42L, 3L);
    total += func_26(20L, 7L);
    total += func_27(69L, 3L);
    total += func_28(24L, 14L);
    total += func_29(37L, 35L);
    total += func_30(17L, 92L);
    total += func_31(57L, 94L);
    total += func_32(2L, 30L);
    total += func_33(12L, 20L);
    total += func_34(2L, 64L);
    total += func_35(28L, 44L);
    total += func_36(54L, 40L);
    total += func_37(64L, 48L);
    total += func_38(60L, 90L);
    total += func_39(5L, 43L);
    total += func_40(11L, 97L);
    total += func_41(19L, 8L);
    total += func_42(35L, 100L);
    total += func_43(51L, 10L);
    total += func_44(70L, 61L);
    total += func_45(24L, 25L);
    total += func_46(33L, 49L);
    total += func_47(2L, 16L);
    total += func_48(99L, 92L);
    total += func_49(32L, 50L);
    total += func_50(99L, 57L);
    total += func_51(32L, 95L);
    total += func_52(5L, 26L);
    total += func_53(59L, 95L);
    total += func_54(99L, 13L);
    total += func_55(67L, 86L);
    total += func_56(27L, 61L);
    total += func_57(50L, 88L);
    total += func_58(40L, 42L);
    total += func_59(21L, 81L);
    total += func_60(94L, 6L);
    total += func_61(96L, 71L);
    total += func_62(67L, 16L);
    total += func_63(33L, 62L);
    total += func_64(82L, 39L);
    total += func_65(26L, 47L);
    total += func_66(7L, 86L);
    total += func_67(28L, 15L);
    total += func_68(31L, 82L);
    total += func_69(56L, 42L);
    total += func_70(2L, 22L);
    total += func_71(36L, 75L);
    total += func_72(16L, 51L);
    total += func_73(32L, 2L);
    total += func_74(6L, 75L);
    total += func_75(89L, 61L);
    total += func_76(89L, 77L);
    total += func_77(20L, 48L);
    total += func_78(99L, 12L);
    total += func_79(32L, 21L);
    total += func_80(64L, 12L);
    total += func_81(88L, 80L);
    total += func_82(44L, 98L);
    total += func_83(81L, 8L);
    total += func_84(8L, 46L);
    total += func_85(83L, 20L);
    total += func_86(90L, 69L);
    total += func_87(14L, 17L);
    total += func_88(63L, 30L);
    total += func_89(41L, 72L);
    total += func_90(83L, 97L);
    total += func_91(45L, 57L);
    total += func_92(94L, 25L);
    total += func_93(3L, 89L);
    total += func_94(49L, 46L);
    total += func_95(93L, 18L);
    total += func_96(33L, 6L);
    total += func_97(63L, 91L);
    total += func_98(57L, 72L);
    total += func_99(38L, 70L);
    total += func_100(90L, 63L);
    total += func_101(25L, 73L);
    total += func_102(24L, 70L);
    total += func_103(45L, 42L);
    total += func_104(94L, 60L);
    total += func_105(36L, 77L);
    total += func_106(71L, 21L);
    total += func_107(9L, 68L);
    total += func_108(20L, 58L);
    total += func_109(38L, 34L);
    total += func_110(70L, 47L);
    total += func_111(59L, 1L);
    total += func_112(100L, 82L);
    total += func_113(65L, 49L);
    total += func_114(94L, 24L);
    total += func_115(3L, 80L);
    total += func_116(47L, 100L);
    total += func_117(80L, 31L);
    total += func_118(42L, 93L);
    total += func_119(9L, 85L);
    total += func_120(69L, 50L);
    total += func_121(25L, 68L);
    total += func_122(88L, 64L);
    total += func_123(99L, 71L);
    total += func_124(20L, 79L);
    total += func_125(37L, 42L);
    total += func_126(53L, 83L);
    total += func_127(42L, 15L);
    total += func_128(13L, 67L);
    total += func_129(85L, 9L);
    total += func_130(6L, 17L);
    total += func_131(23L, 5L);
    total += func_132(26L, 14L);
    total += func_133(63L, 25L);
    total += func_134(13L, 5L);
    total += func_135(74L, 83L);
    total += func_136(50L, 85L);
    total += func_137(63L, 68L);
    total += func_138(80L, 90L);
    total += func_139(76L, 33L);
    total += func_140(7L, 47L);
    total += func_141(29L, 78L);
    total += func_142(92L, 10L);
    total += func_143(2L, 27L);
    total += func_144(84L, 63L);
    total += func_145(11L, 60L);
    total += func_146(82L, 8L);
    total += func_147(47L, 72L);
    total += func_148(96L, 54L);
    total += func_149(48L, 91L);
    total += func_150(8L, 79L);
    total += func_151(35L, 68L);
    total += func_152(6L, 94L);
    total += func_153(10L, 39L);
    total += func_154(10L, 28L);
    total += func_155(67L, 13L);
    total += func_156(13L, 93L);
    total += func_157(30L, 69L);
    total += func_158(50L, 25L);
    total += func_159(25L, 68L);
    total += func_160(85L, 32L);
    total += func_161(73L, 81L);
    total += func_162(23L, 72L);
    total += func_163(96L, 72L);
    total += func_164(54L, 96L);
    total += func_165(14L, 99L);
    total += func_166(82L, 74L);
    total += func_167(46L, 87L);
    total += func_168(59L, 90L);
    total += func_169(86L, 55L);
    total += func_170(14L, 22L);
    total += func_171(24L, 71L);
    total += func_172(52L, 65L);
    total += func_173(44L, 85L);
    total += func_174(21L, 69L);
    total += func_175(77L, 57L);
    total += func_176(46L, 41L);
    total += func_177(71L, 42L);
    total += func_178(48L, 53L);
    total += func_179(98L, 82L);
    total += func_180(56L, 93L);
    total += func_181(42L, 78L);
    total += func_182(31L, 73L);
    total += func_183(70L, 28L);
    total += func_184(49L, 99L);
    total += func_185(71L, 96L);
    total += func_186(33L, 47L);
    total += func_187(58L, 58L);
    total += func_188(51L, 1L);
    total += func_189(93L, 5L);
    total += func_190(37L, 77L);
    total += func_191(3L, 67L);
    total += func_192(18L, 39L);
    total += func_193(1L, 39L);
    total += func_194(29L, 28L);
    total += func_195(41L, 3L);
    total += func_196(99L, 89L);
    total += func_197(36L, 71L);
    total += func_198(66L, 72L);
    total += func_199(74L, 74L);
    total += func_200(20L, 13L);
    total += func_201(5L, 59L);
    total += func_202(46L, 20L);
    total += func_203(18L, 34L);
    total += func_204(47L, 75L);
    total += func_205(32L, 30L);
    total += func_206(33L, 39L);
    total += func_207(12L, 74L);
    total += func_208(52L, 73L);
    total += func_209(28L, 94L);
    total += func_210(10L, 93L);
    total += func_211(42L, 62L);
    total += func_212(23L, 63L);
    total += func_213(89L, 90L);
    total += func_214(74L, 13L);
    total += func_215(77L, 83L);
    total += func_216(39L, 5L);
    total += func_217(94L, 74L);
    total += func_218(49L, 11L);
    total += func_219(100L, 8L);
    total += func_220(99L, 43L);
    total += func_221(45L, 56L);
    total += func_222(54L, 16L);
    total += func_223(99L, 30L);
    total += func_224(96L, 84L);
    total += func_225(78L, 2L);
    total += func_226(82L, 100L);
    total += func_227(81L, 49L);
    total += func_228(7L, 40L);
    total += func_229(68L, 6L);
    total += func_230(41L, 70L);
    total += func_231(73L, 20L);
    total += func_232(42L, 65L);
    total += func_233(90L, 29L);
    total += func_234(20L, 7L);
    total += func_235(87L, 94L);
    total += func_236(51L, 58L);
    total += func_237(97L, 77L);
    total += func_238(74L, 65L);
    total += func_239(12L, 29L);
    total += func_240(56L, 38L);
    total += func_241(51L, 19L);
    total += func_242(17L, 44L);
    total += func_243(11L, 61L);
    total += func_244(74L, 96L);
    total += func_245(7L, 71L);
    total += func_246(52L, 34L);
    total += func_247(11L, 52L);
    total += func_248(65L, 56L);
    total += func_249(100L, 90L);
    total += func_250(17L, 98L);
    total += func_251(18L, 62L);
    total += func_252(72L, 26L);
    total += func_253(63L, 51L);
    total += func_254(84L, 74L);
    total += func_255(26L, 72L);
    total += func_256(79L, 95L);
    total += func_257(68L, 32L);
    total += func_258(32L, 10L);
    total += func_259(35L, 100L);
    total += func_260(56L, 42L);
    total += func_261(88L, 74L);
    total += func_262(12L, 15L);
    total += func_263(86L, 53L);
    total += func_264(55L, 47L);
    total += func_265(45L, 25L);
    total += func_266(42L, 45L);
    total += func_267(77L, 84L);
    total += func_268(4L, 99L);
    total += func_269(40L, 22L);
    total += func_270(45L, 79L);
    total += func_271(57L, 80L);
    total += func_272(19L, 57L);
    total += func_273(6L, 30L);
    total += func_274(26L, 88L);
    total += func_275(48L, 20L);
    total += func_276(97L, 94L);
    total += func_277(11L, 15L);
    total += func_278(95L, 7L);
    total += func_279(32L, 80L);
    total += func_280(19L, 37L);
    total += func_281(2L, 44L);
    total += func_282(89L, 15L);
    total += func_283(40L, 58L);
    total += func_284(61L, 3L);
    total += func_285(43L, 27L);
    total += func_286(95L, 69L);
    total += func_287(28L, 27L);
    total += func_288(70L, 67L);
    total += func_289(97L, 34L);
    total += func_290(71L, 62L);
    total += func_291(80L, 94L);
    total += func_292(19L, 89L);
    total += func_293(90L, 86L);
    total += func_294(3L, 49L);
    total += func_295(75L, 85L);
    total += func_296(68L, 6L);
    total += func_297(33L, 22L);
    total += func_298(8L, 37L);
    total += func_299(26L, 90L);
    total += func_300(80L, 35L);
    total += func_301(7L, 60L);
    total += func_302(84L, 2L);
    total += func_303(9L, 50L);
    total += func_304(85L, 35L);
    total += func_305(85L, 85L);
    total += func_306(47L, 14L);
    total += func_307(3L, 38L);
    total += func_308(84L, 50L);
    total += func_309(30L, 49L);
    total += func_310(66L, 91L);
    total += func_311(13L, 41L);
    total += func_312(63L, 77L);
    total += func_313(69L, 12L);
    total += func_314(24L, 26L);
    total += func_315(65L, 59L);
    total += func_316(72L, 92L);
    total += func_317(3L, 6L);
    total += func_318(32L, 68L);
    total += func_319(40L, 43L);
    total += func_320(63L, 51L);
    total += func_321(96L, 21L);
    total += func_322(3L, 45L);
    total += func_323(88L, 46L);
    total += func_324(46L, 81L);
    total += func_325(39L, 31L);
    total += func_326(65L, 36L);
    total += func_327(8L, 81L);
    total += func_328(33L, 50L);
    total += func_329(4L, 72L);
    total += func_330(36L, 29L);
    total += func_331(20L, 44L);
    total += func_332(51L, 85L);
    total += func_333(18L, 12L);
    total += func_334(94L, 49L);
    total += func_335(67L, 87L);
    total += func_336(79L, 81L);
    total += func_337(88L, 30L);
    total += func_338(54L, 31L);
    total += func_339(74L, 20L);
    total += func_340(55L, 40L);
    total += func_341(78L, 43L);
    total += func_342(58L, 70L);
    total += func_343(17L, 27L);
    total += func_344(84L, 18L);
    total += func_345(75L, 70L);
    total += func_346(88L, 26L);
    total += func_347(18L, 40L);
    total += func_348(89L, 91L);
    total += func_349(68L, 18L);
    total += func_350(56L, 99L);
    total += func_351(19L, 84L);
    total += func_352(73L, 21L);
    total += func_353(41L, 9L);
    total += func_354(72L, 69L);
    total += func_355(93L, 16L);
    total += func_356(24L, 41L);
    total += func_357(19L, 94L);
    total += func_358(4L, 98L);
    total += func_359(41L, 53L);
    total += func_360(53L, 39L);
    total += func_361(57L, 96L);
    total += func_362(82L, 95L);
    total += func_363(36L, 20L);
    total += func_364(100L, 25L);
    total += func_365(14L, 17L);
    total += func_366(24L, 4L);
    total += func_367(98L, 79L);
    total += func_368(79L, 35L);
    total += func_369(78L, 73L);
    total += func_370(79L, 30L);
    total += func_371(77L, 30L);
    total += func_372(30L, 88L);
    total += func_373(4L, 46L);
    total += func_374(11L, 89L);
    total += func_375(100L, 62L);
    total += func_376(18L, 65L);
    total += func_377(78L, 61L);
    total += func_378(92L, 84L);
    total += func_379(48L, 24L);
    total += func_380(50L, 63L);
    total += func_381(61L, 18L);
    total += func_382(21L, 25L);
    total += func_383(29L, 5L);
    total += func_384(53L, 98L);
    total += func_385(2L, 35L);
    total += func_386(53L, 29L);
    total += func_387(96L, 86L);
    total += func_388(26L, 97L);
    total += func_389(27L, 9L);
    total += func_390(23L, 57L);
    total += func_391(79L, 63L);
    total += func_392(89L, 42L);
    total += func_393(59L, 32L);
    total += func_394(55L, 52L);
    total += func_395(100L, 6L);
    total += func_396(78L, 95L);
    total += func_397(49L, 93L);
    total += func_398(41L, 51L);
    total += func_399(79L, 96L);
    total += func_400(74L, 77L);
    total += func_401(69L, 68L);
    total += func_402(83L, 91L);
    total += func_403(5L, 67L);
    total += func_404(14L, 58L);
    total += func_405(59L, 6L);
    total += func_406(32L, 67L);
    total += func_407(69L, 51L);
    total += func_408(95L, 6L);
    total += func_409(72L, 50L);
    total += func_410(67L, 98L);
    total += func_411(81L, 7L);
    total += func_412(25L, 38L);
    total += func_413(57L, 51L);
    total += func_414(39L, 100L);
    total += func_415(37L, 60L);
    total += func_416(22L, 55L);
    total += func_417(38L, 79L);
    total += func_418(7L, 89L);
    total += func_419(67L, 19L);
    total += func_420(60L, 83L);
    total += func_421(58L, 12L);
    total += func_422(93L, 65L);
    total += func_423(15L, 24L);
    total += func_424(100L, 75L);
    total += func_425(90L, 70L);
    total += func_426(18L, 51L);
    total += func_427(53L, 42L);
    total += func_428(58L, 4L);
    total += func_429(23L, 59L);
    total += func_430(76L, 92L);
    total += func_431(26L, 59L);
    total += func_432(12L, 33L);
    total += func_433(42L, 89L);
    total += func_434(84L, 92L);
    total += func_435(21L, 92L);
    total += func_436(94L, 16L);
    total += func_437(12L, 15L);
    total += func_438(91L, 58L);
    total += func_439(82L, 47L);
    total += func_440(11L, 68L);
    total += func_441(91L, 50L);
    total += func_442(94L, 66L);
    total += func_443(79L, 21L);
    total += func_444(49L, 71L);
    total += func_445(49L, 6L);
    total += func_446(99L, 22L);
    total += func_447(43L, 73L);
    total += func_448(85L, 20L);
    total += func_449(21L, 19L);
    total += func_450(23L, 99L);
    total += func_451(92L, 7L);
    total += func_452(54L, 40L);
    total += func_453(40L, 94L);
    total += func_454(99L, 58L);
    total += func_455(37L, 81L);
    total += func_456(24L, 16L);
    total += func_457(17L, 26L);
    total += func_458(1L, 80L);
    total += func_459(98L, 33L);
    total += func_460(2L, 59L);
    total += func_461(64L, 64L);
    total += func_462(70L, 1L);
    total += func_463(78L, 64L);
    total += func_464(31L, 28L);
    total += func_465(76L, 85L);
    total += func_466(61L, 59L);
    total += func_467(53L, 57L);
    total += func_468(11L, 77L);
    total += func_469(77L, 1L);
    total += func_470(32L, 71L);
    total += func_471(36L, 80L);
    total += func_472(81L, 72L);
    total += func_473(27L, 7L);
    total += func_474(24L, 19L);
    total += func_475(8L, 84L);
    total += func_476(45L, 5L);
    total += func_477(19L, 5L);
    total += func_478(86L, 74L);
    total += func_479(78L, 39L);
    total += func_480(43L, 12L);
    total += func_481(7L, 14L);
    total += func_482(54L, 23L);
    total += func_483(21L, 87L);
    total += func_484(37L, 79L);
    total += func_485(85L, 89L);
    total += func_486(90L, 77L);
    total += func_487(74L, 72L);
    total += func_488(23L, 59L);
    total += func_489(96L, 75L);
    total += func_490(47L, 5L);
    total += func_491(12L, 99L);
    total += func_492(39L, 42L);
    total += func_493(48L, 49L);
    total += func_494(9L, 98L);
    total += func_495(55L, 71L);
    total += func_496(9L, 38L);
    total += func_497(61L, 18L);
    total += func_498(16L, 89L);
    total += func_499(36L, 43L);
    printf("Checksum: %ld\n", total);
    return 0;
}
