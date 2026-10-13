#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    long f0;
    unsigned f1;
    double f2;
    char* f3;
    int f4;
    unsigned f5;
    long f6;
} Struct0;

typedef struct {
    long f0;
    double f1;
    char* f2;
    long f3;
    double f4;
    char* f5;
    int f6;
} Struct1;

typedef struct {
    long f0;
    long f1;
    int f2;
    char* f3;
    unsigned f4;
} Struct2;

typedef struct {
    long f0;
    char* f1;
    double f2;
    long f3;
    char* f4;
} Struct3;

typedef struct {
    long f0;
    int f1;
    char* f2;
    char* f3;
    double f4;
    long f5;
} Struct4;

typedef struct {
    unsigned f0;
    double f1;
    double f2;
} Struct5;

typedef struct {
    char* f0;
    long f1;
    char* f2;
    int f3;
    char* f4;
    char* f5;
} Struct6;

typedef struct {
    char* f0;
    long f1;
    unsigned f2;
} Struct7;

typedef struct {
    double f0;
    int f1;
    double f2;
} Struct8;

typedef struct {
    double f0;
    int f1;
    double f2;
    unsigned f3;
    long f4;
    int f5;
    char* f6;
    long f7;
} Struct9;

typedef struct {
    int f0;
    long f1;
    char* f2;
    double f3;
    unsigned f4;
} Struct10;

typedef struct {
    long f0;
    char* f1;
    unsigned f2;
    double f3;
    long f4;
    unsigned f5;
} Struct11;

typedef struct {
    int f0;
    int f1;
    int f2;
    int f3;
    unsigned f4;
    double f5;
    unsigned f6;
    char* f7;
} Struct12;

typedef struct {
    unsigned f0;
    unsigned f1;
    char* f2;
} Struct13;

typedef struct {
    long f0;
    long f1;
    long f2;
    unsigned f3;
    char* f4;
    long f5;
    int f6;
    long f7;
} Struct14;

typedef struct {
    double f0;
    char* f1;
    int f2;
    int f3;
    unsigned f4;
} Struct15;

typedef struct {
    double f0;
    char* f1;
    int f2;
    long f3;
    double f4;
    double f5;
    int f6;
} Struct16;

typedef struct {
    long f0;
    double f1;
    char* f2;
    long f3;
    char* f4;
} Struct17;

typedef struct {
    unsigned f0;
    double f1;
    long f2;
} Struct18;

typedef struct {
    double f0;
    long f1;
    int f2;
} Struct19;

typedef struct {
    char* f0;
    unsigned f1;
    char* f2;
} Struct20;

typedef struct {
    unsigned f0;
    int f1;
    double f2;
    long f3;
    double f4;
    char* f5;
    long f6;
    unsigned f7;
} Struct21;

typedef struct {
    unsigned f0;
    double f1;
    double f2;
    int f3;
    long f4;
    double f5;
    double f6;
} Struct22;

typedef struct {
    double f0;
    char* f1;
    char* f2;
    int f3;
    long f4;
    unsigned f5;
    int f6;
    long f7;
} Struct23;

typedef struct {
    int f0;
    long f1;
    double f2;
    int f3;
} Struct24;

typedef struct {
    int f0;
    char* f1;
    long f2;
    double f3;
    unsigned f4;
} Struct25;

typedef struct {
    unsigned f0;
    long f1;
    long f2;
    char* f3;
    unsigned f4;
    unsigned f5;
    double f6;
    double f7;
} Struct26;

typedef struct {
    double f0;
    double f1;
    long f2;
    char* f3;
    long f4;
    char* f5;
    double f6;
    int f7;
} Struct27;

typedef struct {
    int f0;
    unsigned f1;
    double f2;
    char* f3;
} Struct28;

typedef struct {
    int f0;
    double f1;
    unsigned f2;
    long f3;
    int f4;
    char* f5;
} Struct29;

long process_0(Struct19* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 8;
    }
    return sum;
}

long process_1(Struct29* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 58;
        p[i].f0 = (int)(sum % 2450);
    }
    return sum;
}

long process_2(Struct15* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 96;
        p[i].f0 = (int)(sum % 1108);
    }
    return sum;
}

long process_3(Struct1* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 89;
        p[i].f0 = (int)(sum % 2085);
    }
    return sum;
}

long process_4(Struct22* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 12;
        p[i].f0 = (int)(sum % 7468);
    }
    return sum;
}

long process_5(Struct10* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 67;
        p[i].f0 = (int)(sum % 2505);
    }
    return sum;
}

long process_6(Struct15* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 92;
        p[i].f0 = (int)(sum % 1880);
    }
    return sum;
}

long process_7(Struct8* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 1;
    }
    return sum;
}

long process_8(Struct6* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 83;
        p[i].f0 = (int)(sum % 1674);
    }
    return sum;
}

long process_9(Struct7* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 94;
    }
    return sum;
}

long process_10(Struct5* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 23;
        p[i].f0 = (int)(sum % 9722);
    }
    return sum;
}

long process_11(Struct25* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 86;
        p[i].f0 = (int)(sum % 3244);
    }
    return sum;
}

long process_12(Struct14* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 18;
    }
    return sum;
}

long process_13(Struct6* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 67;
        p[i].f0 = (int)(sum % 8475);
    }
    return sum;
}

long process_14(Struct28* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 30;
    }
    return sum;
}

long process_15(Struct16* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 2;
    }
    return sum;
}

long process_16(Struct29* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 66;
        p[i].f0 = (int)(sum % 9551);
    }
    return sum;
}

long process_17(Struct21* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 62;
        p[i].f0 = (int)(sum % 1897);
    }
    return sum;
}

long process_18(Struct3* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 6;
    }
    return sum;
}

long process_19(Struct18* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 92;
        p[i].f0 = (int)(sum % 9971);
    }
    return sum;
}

long process_20(Struct2* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 36;
    }
    return sum;
}

long process_21(Struct4* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 90;
    }
    return sum;
}

long process_22(Struct9* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 88;
        p[i].f0 = (int)(sum % 1677);
    }
    return sum;
}

long process_23(Struct9* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 37;
    }
    return sum;
}

long process_24(Struct23* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 50;
        p[i].f0 = (int)(sum % 6309);
    }
    return sum;
}

long process_25(Struct4* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 91;
        p[i].f0 = (int)(sum % 5548);
    }
    return sum;
}

long process_26(Struct22* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 5;
    }
    return sum;
}

long process_27(Struct12* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 31;
    }
    return sum;
}

long process_28(Struct6* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 53;
    }
    return sum;
}

long process_29(Struct5* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 64;
    }
    return sum;
}

long process_30(Struct29* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 25;
        p[i].f0 = (int)(sum % 545);
    }
    return sum;
}

long process_31(Struct24* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 25;
    }
    return sum;
}

long process_32(Struct1* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 29;
    }
    return sum;
}

long process_33(Struct8* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 5;
        p[i].f0 = (int)(sum % 6246);
    }
    return sum;
}

long process_34(Struct4* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 33;
        p[i].f0 = (int)(sum % 6150);
    }
    return sum;
}

long process_35(Struct24* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 59;
        p[i].f0 = (int)(sum % 4422);
    }
    return sum;
}

long process_36(Struct27* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 8;
    }
    return sum;
}

long process_37(Struct9* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 12;
    }
    return sum;
}

long process_38(Struct0* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 48;
    }
    return sum;
}

long process_39(Struct1* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 50;
    }
    return sum;
}

long process_40(Struct1* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 30;
    }
    return sum;
}

long process_41(Struct4* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 63;
        p[i].f0 = (int)(sum % 1808);
    }
    return sum;
}

long process_42(Struct29* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 94;
    }
    return sum;
}

long process_43(Struct22* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 85;
        p[i].f0 = (int)(sum % 7283);
    }
    return sum;
}

long process_44(Struct8* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 48;
        p[i].f0 = (int)(sum % 3614);
    }
    return sum;
}

long process_45(Struct21* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 77;
    }
    return sum;
}

long process_46(Struct12* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 18;
        p[i].f0 = (int)(sum % 8559);
    }
    return sum;
}

long process_47(Struct21* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 63;
    }
    return sum;
}

long process_48(Struct7* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 54;
        p[i].f0 = (int)(sum % 8710);
    }
    return sum;
}

long process_49(Struct1* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 7;
        p[i].f0 = (int)(sum % 275);
    }
    return sum;
}

long process_50(Struct24* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 90;
    }
    return sum;
}

long process_51(Struct14* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 81;
    }
    return sum;
}

long process_52(Struct9* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 18;
    }
    return sum;
}

long process_53(Struct15* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 32;
        p[i].f0 = (int)(sum % 7353);
    }
    return sum;
}

long process_54(Struct23* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 9;
    }
    return sum;
}

long process_55(Struct19* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 98;
    }
    return sum;
}

long process_56(Struct17* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 8;
        p[i].f0 = (int)(sum % 7534);
    }
    return sum;
}

long process_57(Struct8* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 45;
        p[i].f0 = (int)(sum % 2796);
    }
    return sum;
}

long process_58(Struct24* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 10;
        p[i].f0 = (int)(sum % 3928);
    }
    return sum;
}

long process_59(Struct27* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 97;
        p[i].f0 = (int)(sum % 8927);
    }
    return sum;
}

long process_60(Struct16* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 99;
        p[i].f0 = (int)(sum % 6957);
    }
    return sum;
}

long process_61(Struct24* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 23;
        p[i].f0 = (int)(sum % 992);
    }
    return sum;
}

long process_62(Struct11* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 95;
        p[i].f0 = (int)(sum % 1790);
    }
    return sum;
}

long process_63(Struct0* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 22;
    }
    return sum;
}

long process_64(Struct22* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 21;
        p[i].f0 = (int)(sum % 9314);
    }
    return sum;
}

long process_65(Struct23* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 37;
        p[i].f0 = (int)(sum % 9633);
    }
    return sum;
}

long process_66(Struct28* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 87;
        p[i].f0 = (int)(sum % 9149);
    }
    return sum;
}

long process_67(Struct18* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 94;
        p[i].f0 = (int)(sum % 3261);
    }
    return sum;
}

long process_68(Struct4* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 7;
        p[i].f0 = (int)(sum % 7903);
    }
    return sum;
}

long process_69(Struct3* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 78;
    }
    return sum;
}

long process_70(Struct15* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 40;
    }
    return sum;
}

long process_71(Struct5* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 21;
    }
    return sum;
}

long process_72(Struct15* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 8;
    }
    return sum;
}

long process_73(Struct25* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 10;
        p[i].f0 = (int)(sum % 3035);
    }
    return sum;
}

long process_74(Struct21* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 1;
    }
    return sum;
}

long process_75(Struct10* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 5;
    }
    return sum;
}

long process_76(Struct7* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 82;
    }
    return sum;
}

long process_77(Struct23* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 53;
    }
    return sum;
}

long process_78(Struct27* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 26;
    }
    return sum;
}

long process_79(Struct24* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 75;
    }
    return sum;
}

long process_80(Struct28* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 90;
    }
    return sum;
}

long process_81(Struct7* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 74;
    }
    return sum;
}

long process_82(Struct9* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 67;
        p[i].f0 = (int)(sum % 2687);
    }
    return sum;
}

long process_83(Struct21* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 19;
        p[i].f0 = (int)(sum % 281);
    }
    return sum;
}

long process_84(Struct12* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 14;
        p[i].f0 = (int)(sum % 3059);
    }
    return sum;
}

long process_85(Struct8* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 28;
    }
    return sum;
}

long process_86(Struct29* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 74;
    }
    return sum;
}

long process_87(Struct3* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 11;
    }
    return sum;
}

long process_88(Struct21* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 51;
        p[i].f0 = (int)(sum % 290);
    }
    return sum;
}

long process_89(Struct9* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 23;
        p[i].f0 = (int)(sum % 8314);
    }
    return sum;
}

long process_90(Struct19* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 96;
    }
    return sum;
}

long process_91(Struct29* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 91;
        p[i].f0 = (int)(sum % 1441);
    }
    return sum;
}

long process_92(Struct21* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 23;
    }
    return sum;
}

long process_93(Struct28* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 72;
        p[i].f0 = (int)(sum % 5142);
    }
    return sum;
}

long process_94(Struct25* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 1;
    }
    return sum;
}

long process_95(Struct1* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 50;
    }
    return sum;
}

long process_96(Struct22* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 65;
    }
    return sum;
}

long process_97(Struct27* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 83;
        p[i].f0 = (int)(sum % 8757);
    }
    return sum;
}

long process_98(Struct15* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 90;
    }
    return sum;
}

long process_99(Struct25* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 47;
    }
    return sum;
}

long process_100(Struct15* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 60;
        p[i].f0 = (int)(sum % 3965);
    }
    return sum;
}

long process_101(Struct9* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 57;
    }
    return sum;
}

long process_102(Struct13* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 86;
    }
    return sum;
}

long process_103(Struct22* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 5;
        p[i].f0 = (int)(sum % 5798);
    }
    return sum;
}

long process_104(Struct15* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 6;
        p[i].f0 = (int)(sum % 6094);
    }
    return sum;
}

long process_105(Struct11* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 74;
    }
    return sum;
}

long process_106(Struct2* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 8;
    }
    return sum;
}

long process_107(Struct26* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 60;
    }
    return sum;
}

long process_108(Struct7* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 36;
        p[i].f0 = (int)(sum % 2955);
    }
    return sum;
}

long process_109(Struct26* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 69;
    }
    return sum;
}

long process_110(Struct4* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 67;
        p[i].f0 = (int)(sum % 4488);
    }
    return sum;
}

long process_111(Struct25* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 75;
    }
    return sum;
}

long process_112(Struct22* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 19;
    }
    return sum;
}

long process_113(Struct19* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 4;
        p[i].f0 = (int)(sum % 6894);
    }
    return sum;
}

long process_114(Struct21* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 41;
        p[i].f0 = (int)(sum % 6212);
    }
    return sum;
}

long process_115(Struct18* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 44;
        p[i].f0 = (int)(sum % 6915);
    }
    return sum;
}

long process_116(Struct21* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 66;
        p[i].f0 = (int)(sum % 3804);
    }
    return sum;
}

long process_117(Struct13* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 8;
    }
    return sum;
}

long process_118(Struct11* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 26;
    }
    return sum;
}

long process_119(Struct10* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 22;
    }
    return sum;
}

long process_120(Struct21* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 40;
    }
    return sum;
}

long process_121(Struct17* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 35;
    }
    return sum;
}

long process_122(Struct0* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 94;
    }
    return sum;
}

long process_123(Struct22* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 5;
        p[i].f0 = (int)(sum % 4808);
    }
    return sum;
}

long process_124(Struct20* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 75;
    }
    return sum;
}

long process_125(Struct14* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 44;
        p[i].f0 = (int)(sum % 6667);
    }
    return sum;
}

long process_126(Struct26* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 49;
    }
    return sum;
}

long process_127(Struct10* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 94;
    }
    return sum;
}

long process_128(Struct18* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 14;
    }
    return sum;
}

long process_129(Struct17* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 61;
        p[i].f0 = (int)(sum % 1312);
    }
    return sum;
}

long process_130(Struct13* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 26;
    }
    return sum;
}

long process_131(Struct7* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 63;
    }
    return sum;
}

long process_132(Struct2* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 67;
        p[i].f0 = (int)(sum % 8715);
    }
    return sum;
}

long process_133(Struct18* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 37;
    }
    return sum;
}

long process_134(Struct12* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 60;
    }
    return sum;
}

long process_135(Struct5* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 37;
    }
    return sum;
}

long process_136(Struct21* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 21;
    }
    return sum;
}

long process_137(Struct6* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 88;
        p[i].f0 = (int)(sum % 4658);
    }
    return sum;
}

long process_138(Struct1* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 93;
        p[i].f0 = (int)(sum % 5825);
    }
    return sum;
}

long process_139(Struct19* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 94;
        p[i].f0 = (int)(sum % 6742);
    }
    return sum;
}

long process_140(Struct1* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 86;
    }
    return sum;
}

long process_141(Struct21* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 68;
        p[i].f0 = (int)(sum % 828);
    }
    return sum;
}

long process_142(Struct28* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 70;
    }
    return sum;
}

long process_143(Struct6* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 62;
    }
    return sum;
}

long process_144(Struct12* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 20;
    }
    return sum;
}

long process_145(Struct12* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 68;
        p[i].f0 = (int)(sum % 8295);
    }
    return sum;
}

long process_146(Struct27* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 11;
        p[i].f0 = (int)(sum % 8517);
    }
    return sum;
}

long process_147(Struct0* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 53;
    }
    return sum;
}

long process_148(Struct20* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 59;
        p[i].f0 = (int)(sum % 2687);
    }
    return sum;
}

long process_149(Struct21* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 96;
    }
    return sum;
}

long process_150(Struct18* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 71;
    }
    return sum;
}

long process_151(Struct3* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 24;
    }
    return sum;
}

long process_152(Struct14* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 24;
        p[i].f0 = (int)(sum % 3772);
    }
    return sum;
}

long process_153(Struct1* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 67;
        p[i].f0 = (int)(sum % 9988);
    }
    return sum;
}

long process_154(Struct22* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 1;
    }
    return sum;
}

long process_155(Struct6* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 43;
    }
    return sum;
}

long process_156(Struct2* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 16;
    }
    return sum;
}

long process_157(Struct6* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 79;
        p[i].f0 = (int)(sum % 4172);
    }
    return sum;
}

long process_158(Struct15* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 72;
    }
    return sum;
}

long process_159(Struct26* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 90;
        p[i].f0 = (int)(sum % 1169);
    }
    return sum;
}

long process_160(Struct7* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 41;
    }
    return sum;
}

long process_161(Struct1* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 78;
        p[i].f0 = (int)(sum % 3059);
    }
    return sum;
}

long process_162(Struct29* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 36;
        p[i].f0 = (int)(sum % 274);
    }
    return sum;
}

long process_163(Struct27* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 5;
    }
    return sum;
}

long process_164(Struct2* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 10;
        p[i].f0 = (int)(sum % 6588);
    }
    return sum;
}

long process_165(Struct29* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 37;
        p[i].f0 = (int)(sum % 1101);
    }
    return sum;
}

long process_166(Struct28* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 92;
    }
    return sum;
}

long process_167(Struct17* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 15;
    }
    return sum;
}

long process_168(Struct20* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 35;
        p[i].f0 = (int)(sum % 1941);
    }
    return sum;
}

long process_169(Struct24* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 63;
    }
    return sum;
}

long process_170(Struct4* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 92;
    }
    return sum;
}

long process_171(Struct14* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 74;
        p[i].f0 = (int)(sum % 3994);
    }
    return sum;
}

long process_172(Struct10* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 73;
    }
    return sum;
}

long process_173(Struct20* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 57;
    }
    return sum;
}

long process_174(Struct23* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 33;
        p[i].f0 = (int)(sum % 9064);
    }
    return sum;
}

long process_175(Struct20* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 30;
    }
    return sum;
}

long process_176(Struct25* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 5;
    }
    return sum;
}

long process_177(Struct15* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 42;
        p[i].f0 = (int)(sum % 9006);
    }
    return sum;
}

long process_178(Struct9* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 15;
        p[i].f0 = (int)(sum % 4694);
    }
    return sum;
}

long process_179(Struct11* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 36;
    }
    return sum;
}

long process_180(Struct7* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 53;
    }
    return sum;
}

long process_181(Struct19* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 88;
    }
    return sum;
}

long process_182(Struct0* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 68;
    }
    return sum;
}

long process_183(Struct7* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 14;
    }
    return sum;
}

long process_184(Struct19* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 68;
        p[i].f0 = (int)(sum % 9756);
    }
    return sum;
}

long process_185(Struct16* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 64;
    }
    return sum;
}

long process_186(Struct20* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 43;
    }
    return sum;
}

long process_187(Struct24* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 68;
    }
    return sum;
}

long process_188(Struct26* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 90;
    }
    return sum;
}

long process_189(Struct6* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 55;
        p[i].f0 = (int)(sum % 1882);
    }
    return sum;
}

long process_190(Struct8* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 23;
    }
    return sum;
}

long process_191(Struct23* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 36;
    }
    return sum;
}

long process_192(Struct25* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 69;
    }
    return sum;
}

long process_193(Struct18* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 88;
        p[i].f0 = (int)(sum % 4779);
    }
    return sum;
}

long process_194(Struct17* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 9;
        p[i].f0 = (int)(sum % 4826);
    }
    return sum;
}

long process_195(Struct22* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 18;
        p[i].f0 = (int)(sum % 165);
    }
    return sum;
}

long process_196(Struct5* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 64;
    }
    return sum;
}

long process_197(Struct0* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 47;
    }
    return sum;
}

long process_198(Struct8* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 89;
        p[i].f0 = (int)(sum % 8170);
    }
    return sum;
}

long process_199(Struct2* p, int n) {
    long sum = 0;
    for (int i = 0; i < n; i++) {
        sum += p[i].f0 * 29;
    }
    return sum;
}

int main(void) {
    long total = 0;
    Struct14 arr0[10];
    memset(arr0, 0, sizeof(arr0));
    for (int j = 0; j < 10; j++) arr0[j].f0 = j + 0;
    total += process_0(arr0, 10);
    Struct29 arr1[10];
    memset(arr1, 0, sizeof(arr1));
    for (int j = 0; j < 10; j++) arr1[j].f0 = j + 1;
    total += process_1(arr1, 10);
    Struct20 arr2[10];
    memset(arr2, 0, sizeof(arr2));
    for (int j = 0; j < 10; j++) arr2[j].f0 = j + 2;
    total += process_2(arr2, 10);
    Struct13 arr3[10];
    memset(arr3, 0, sizeof(arr3));
    for (int j = 0; j < 10; j++) arr3[j].f0 = j + 3;
    total += process_3(arr3, 10);
    Struct4 arr4[10];
    memset(arr4, 0, sizeof(arr4));
    for (int j = 0; j < 10; j++) arr4[j].f0 = j + 4;
    total += process_4(arr4, 10);
    Struct6 arr5[10];
    memset(arr5, 0, sizeof(arr5));
    for (int j = 0; j < 10; j++) arr5[j].f0 = j + 5;
    total += process_5(arr5, 10);
    Struct28 arr6[10];
    memset(arr6, 0, sizeof(arr6));
    for (int j = 0; j < 10; j++) arr6[j].f0 = j + 6;
    total += process_6(arr6, 10);
    Struct8 arr7[10];
    memset(arr7, 0, sizeof(arr7));
    for (int j = 0; j < 10; j++) arr7[j].f0 = j + 7;
    total += process_7(arr7, 10);
    Struct17 arr8[10];
    memset(arr8, 0, sizeof(arr8));
    for (int j = 0; j < 10; j++) arr8[j].f0 = j + 8;
    total += process_8(arr8, 10);
    Struct18 arr9[10];
    memset(arr9, 0, sizeof(arr9));
    for (int j = 0; j < 10; j++) arr9[j].f0 = j + 9;
    total += process_9(arr9, 10);
    Struct13 arr10[10];
    memset(arr10, 0, sizeof(arr10));
    for (int j = 0; j < 10; j++) arr10[j].f0 = j + 10;
    total += process_10(arr10, 10);
    Struct20 arr11[10];
    memset(arr11, 0, sizeof(arr11));
    for (int j = 0; j < 10; j++) arr11[j].f0 = j + 11;
    total += process_11(arr11, 10);
    Struct17 arr12[10];
    memset(arr12, 0, sizeof(arr12));
    for (int j = 0; j < 10; j++) arr12[j].f0 = j + 12;
    total += process_12(arr12, 10);
    Struct20 arr13[10];
    memset(arr13, 0, sizeof(arr13));
    for (int j = 0; j < 10; j++) arr13[j].f0 = j + 13;
    total += process_13(arr13, 10);
    Struct28 arr14[10];
    memset(arr14, 0, sizeof(arr14));
    for (int j = 0; j < 10; j++) arr14[j].f0 = j + 14;
    total += process_14(arr14, 10);
    Struct22 arr15[10];
    memset(arr15, 0, sizeof(arr15));
    for (int j = 0; j < 10; j++) arr15[j].f0 = j + 15;
    total += process_15(arr15, 10);
    Struct19 arr16[10];
    memset(arr16, 0, sizeof(arr16));
    for (int j = 0; j < 10; j++) arr16[j].f0 = j + 16;
    total += process_16(arr16, 10);
    Struct20 arr17[10];
    memset(arr17, 0, sizeof(arr17));
    for (int j = 0; j < 10; j++) arr17[j].f0 = j + 17;
    total += process_17(arr17, 10);
    Struct10 arr18[10];
    memset(arr18, 0, sizeof(arr18));
    for (int j = 0; j < 10; j++) arr18[j].f0 = j + 18;
    total += process_18(arr18, 10);
    Struct22 arr19[10];
    memset(arr19, 0, sizeof(arr19));
    for (int j = 0; j < 10; j++) arr19[j].f0 = j + 19;
    total += process_19(arr19, 10);
    Struct5 arr20[10];
    memset(arr20, 0, sizeof(arr20));
    for (int j = 0; j < 10; j++) arr20[j].f0 = j + 20;
    total += process_20(arr20, 10);
    Struct13 arr21[10];
    memset(arr21, 0, sizeof(arr21));
    for (int j = 0; j < 10; j++) arr21[j].f0 = j + 21;
    total += process_21(arr21, 10);
    Struct15 arr22[10];
    memset(arr22, 0, sizeof(arr22));
    for (int j = 0; j < 10; j++) arr22[j].f0 = j + 22;
    total += process_22(arr22, 10);
    Struct21 arr23[10];
    memset(arr23, 0, sizeof(arr23));
    for (int j = 0; j < 10; j++) arr23[j].f0 = j + 23;
    total += process_23(arr23, 10);
    Struct3 arr24[10];
    memset(arr24, 0, sizeof(arr24));
    for (int j = 0; j < 10; j++) arr24[j].f0 = j + 24;
    total += process_24(arr24, 10);
    Struct7 arr25[10];
    memset(arr25, 0, sizeof(arr25));
    for (int j = 0; j < 10; j++) arr25[j].f0 = j + 25;
    total += process_25(arr25, 10);
    Struct28 arr26[10];
    memset(arr26, 0, sizeof(arr26));
    for (int j = 0; j < 10; j++) arr26[j].f0 = j + 26;
    total += process_26(arr26, 10);
    Struct11 arr27[10];
    memset(arr27, 0, sizeof(arr27));
    for (int j = 0; j < 10; j++) arr27[j].f0 = j + 27;
    total += process_27(arr27, 10);
    Struct27 arr28[10];
    memset(arr28, 0, sizeof(arr28));
    for (int j = 0; j < 10; j++) arr28[j].f0 = j + 28;
    total += process_28(arr28, 10);
    Struct12 arr29[10];
    memset(arr29, 0, sizeof(arr29));
    for (int j = 0; j < 10; j++) arr29[j].f0 = j + 29;
    total += process_29(arr29, 10);
    Struct16 arr30[10];
    memset(arr30, 0, sizeof(arr30));
    for (int j = 0; j < 10; j++) arr30[j].f0 = j + 30;
    total += process_30(arr30, 10);
    Struct14 arr31[10];
    memset(arr31, 0, sizeof(arr31));
    for (int j = 0; j < 10; j++) arr31[j].f0 = j + 31;
    total += process_31(arr31, 10);
    Struct25 arr32[10];
    memset(arr32, 0, sizeof(arr32));
    for (int j = 0; j < 10; j++) arr32[j].f0 = j + 32;
    total += process_32(arr32, 10);
    Struct27 arr33[10];
    memset(arr33, 0, sizeof(arr33));
    for (int j = 0; j < 10; j++) arr33[j].f0 = j + 33;
    total += process_33(arr33, 10);
    Struct3 arr34[10];
    memset(arr34, 0, sizeof(arr34));
    for (int j = 0; j < 10; j++) arr34[j].f0 = j + 34;
    total += process_34(arr34, 10);
    Struct0 arr35[10];
    memset(arr35, 0, sizeof(arr35));
    for (int j = 0; j < 10; j++) arr35[j].f0 = j + 35;
    total += process_35(arr35, 10);
    Struct8 arr36[10];
    memset(arr36, 0, sizeof(arr36));
    for (int j = 0; j < 10; j++) arr36[j].f0 = j + 36;
    total += process_36(arr36, 10);
    Struct13 arr37[10];
    memset(arr37, 0, sizeof(arr37));
    for (int j = 0; j < 10; j++) arr37[j].f0 = j + 37;
    total += process_37(arr37, 10);
    Struct15 arr38[10];
    memset(arr38, 0, sizeof(arr38));
    for (int j = 0; j < 10; j++) arr38[j].f0 = j + 38;
    total += process_38(arr38, 10);
    Struct10 arr39[10];
    memset(arr39, 0, sizeof(arr39));
    for (int j = 0; j < 10; j++) arr39[j].f0 = j + 39;
    total += process_39(arr39, 10);
    Struct27 arr40[10];
    memset(arr40, 0, sizeof(arr40));
    for (int j = 0; j < 10; j++) arr40[j].f0 = j + 40;
    total += process_40(arr40, 10);
    Struct11 arr41[10];
    memset(arr41, 0, sizeof(arr41));
    for (int j = 0; j < 10; j++) arr41[j].f0 = j + 41;
    total += process_41(arr41, 10);
    Struct22 arr42[10];
    memset(arr42, 0, sizeof(arr42));
    for (int j = 0; j < 10; j++) arr42[j].f0 = j + 42;
    total += process_42(arr42, 10);
    Struct19 arr43[10];
    memset(arr43, 0, sizeof(arr43));
    for (int j = 0; j < 10; j++) arr43[j].f0 = j + 43;
    total += process_43(arr43, 10);
    Struct18 arr44[10];
    memset(arr44, 0, sizeof(arr44));
    for (int j = 0; j < 10; j++) arr44[j].f0 = j + 44;
    total += process_44(arr44, 10);
    Struct15 arr45[10];
    memset(arr45, 0, sizeof(arr45));
    for (int j = 0; j < 10; j++) arr45[j].f0 = j + 45;
    total += process_45(arr45, 10);
    Struct22 arr46[10];
    memset(arr46, 0, sizeof(arr46));
    for (int j = 0; j < 10; j++) arr46[j].f0 = j + 46;
    total += process_46(arr46, 10);
    Struct5 arr47[10];
    memset(arr47, 0, sizeof(arr47));
    for (int j = 0; j < 10; j++) arr47[j].f0 = j + 47;
    total += process_47(arr47, 10);
    Struct25 arr48[10];
    memset(arr48, 0, sizeof(arr48));
    for (int j = 0; j < 10; j++) arr48[j].f0 = j + 48;
    total += process_48(arr48, 10);
    Struct10 arr49[10];
    memset(arr49, 0, sizeof(arr49));
    for (int j = 0; j < 10; j++) arr49[j].f0 = j + 49;
    total += process_49(arr49, 10);
    Struct4 arr50[10];
    memset(arr50, 0, sizeof(arr50));
    for (int j = 0; j < 10; j++) arr50[j].f0 = j + 50;
    total += process_50(arr50, 10);
    Struct22 arr51[10];
    memset(arr51, 0, sizeof(arr51));
    for (int j = 0; j < 10; j++) arr51[j].f0 = j + 51;
    total += process_51(arr51, 10);
    Struct29 arr52[10];
    memset(arr52, 0, sizeof(arr52));
    for (int j = 0; j < 10; j++) arr52[j].f0 = j + 52;
    total += process_52(arr52, 10);
    Struct21 arr53[10];
    memset(arr53, 0, sizeof(arr53));
    for (int j = 0; j < 10; j++) arr53[j].f0 = j + 53;
    total += process_53(arr53, 10);
    Struct18 arr54[10];
    memset(arr54, 0, sizeof(arr54));
    for (int j = 0; j < 10; j++) arr54[j].f0 = j + 54;
    total += process_54(arr54, 10);
    Struct24 arr55[10];
    memset(arr55, 0, sizeof(arr55));
    for (int j = 0; j < 10; j++) arr55[j].f0 = j + 55;
    total += process_55(arr55, 10);
    Struct3 arr56[10];
    memset(arr56, 0, sizeof(arr56));
    for (int j = 0; j < 10; j++) arr56[j].f0 = j + 56;
    total += process_56(arr56, 10);
    Struct9 arr57[10];
    memset(arr57, 0, sizeof(arr57));
    for (int j = 0; j < 10; j++) arr57[j].f0 = j + 57;
    total += process_57(arr57, 10);
    Struct4 arr58[10];
    memset(arr58, 0, sizeof(arr58));
    for (int j = 0; j < 10; j++) arr58[j].f0 = j + 58;
    total += process_58(arr58, 10);
    Struct19 arr59[10];
    memset(arr59, 0, sizeof(arr59));
    for (int j = 0; j < 10; j++) arr59[j].f0 = j + 59;
    total += process_59(arr59, 10);
    Struct25 arr60[10];
    memset(arr60, 0, sizeof(arr60));
    for (int j = 0; j < 10; j++) arr60[j].f0 = j + 60;
    total += process_60(arr60, 10);
    Struct17 arr61[10];
    memset(arr61, 0, sizeof(arr61));
    for (int j = 0; j < 10; j++) arr61[j].f0 = j + 61;
    total += process_61(arr61, 10);
    Struct17 arr62[10];
    memset(arr62, 0, sizeof(arr62));
    for (int j = 0; j < 10; j++) arr62[j].f0 = j + 62;
    total += process_62(arr62, 10);
    Struct29 arr63[10];
    memset(arr63, 0, sizeof(arr63));
    for (int j = 0; j < 10; j++) arr63[j].f0 = j + 63;
    total += process_63(arr63, 10);
    Struct20 arr64[10];
    memset(arr64, 0, sizeof(arr64));
    for (int j = 0; j < 10; j++) arr64[j].f0 = j + 64;
    total += process_64(arr64, 10);
    Struct27 arr65[10];
    memset(arr65, 0, sizeof(arr65));
    for (int j = 0; j < 10; j++) arr65[j].f0 = j + 65;
    total += process_65(arr65, 10);
    Struct17 arr66[10];
    memset(arr66, 0, sizeof(arr66));
    for (int j = 0; j < 10; j++) arr66[j].f0 = j + 66;
    total += process_66(arr66, 10);
    Struct17 arr67[10];
    memset(arr67, 0, sizeof(arr67));
    for (int j = 0; j < 10; j++) arr67[j].f0 = j + 67;
    total += process_67(arr67, 10);
    Struct13 arr68[10];
    memset(arr68, 0, sizeof(arr68));
    for (int j = 0; j < 10; j++) arr68[j].f0 = j + 68;
    total += process_68(arr68, 10);
    Struct23 arr69[10];
    memset(arr69, 0, sizeof(arr69));
    for (int j = 0; j < 10; j++) arr69[j].f0 = j + 69;
    total += process_69(arr69, 10);
    Struct24 arr70[10];
    memset(arr70, 0, sizeof(arr70));
    for (int j = 0; j < 10; j++) arr70[j].f0 = j + 70;
    total += process_70(arr70, 10);
    Struct15 arr71[10];
    memset(arr71, 0, sizeof(arr71));
    for (int j = 0; j < 10; j++) arr71[j].f0 = j + 71;
    total += process_71(arr71, 10);
    Struct8 arr72[10];
    memset(arr72, 0, sizeof(arr72));
    for (int j = 0; j < 10; j++) arr72[j].f0 = j + 72;
    total += process_72(arr72, 10);
    Struct9 arr73[10];
    memset(arr73, 0, sizeof(arr73));
    for (int j = 0; j < 10; j++) arr73[j].f0 = j + 73;
    total += process_73(arr73, 10);
    Struct28 arr74[10];
    memset(arr74, 0, sizeof(arr74));
    for (int j = 0; j < 10; j++) arr74[j].f0 = j + 74;
    total += process_74(arr74, 10);
    Struct16 arr75[10];
    memset(arr75, 0, sizeof(arr75));
    for (int j = 0; j < 10; j++) arr75[j].f0 = j + 75;
    total += process_75(arr75, 10);
    Struct27 arr76[10];
    memset(arr76, 0, sizeof(arr76));
    for (int j = 0; j < 10; j++) arr76[j].f0 = j + 76;
    total += process_76(arr76, 10);
    Struct3 arr77[10];
    memset(arr77, 0, sizeof(arr77));
    for (int j = 0; j < 10; j++) arr77[j].f0 = j + 77;
    total += process_77(arr77, 10);
    Struct17 arr78[10];
    memset(arr78, 0, sizeof(arr78));
    for (int j = 0; j < 10; j++) arr78[j].f0 = j + 78;
    total += process_78(arr78, 10);
    Struct1 arr79[10];
    memset(arr79, 0, sizeof(arr79));
    for (int j = 0; j < 10; j++) arr79[j].f0 = j + 79;
    total += process_79(arr79, 10);
    Struct15 arr80[10];
    memset(arr80, 0, sizeof(arr80));
    for (int j = 0; j < 10; j++) arr80[j].f0 = j + 80;
    total += process_80(arr80, 10);
    Struct1 arr81[10];
    memset(arr81, 0, sizeof(arr81));
    for (int j = 0; j < 10; j++) arr81[j].f0 = j + 81;
    total += process_81(arr81, 10);
    Struct7 arr82[10];
    memset(arr82, 0, sizeof(arr82));
    for (int j = 0; j < 10; j++) arr82[j].f0 = j + 82;
    total += process_82(arr82, 10);
    Struct11 arr83[10];
    memset(arr83, 0, sizeof(arr83));
    for (int j = 0; j < 10; j++) arr83[j].f0 = j + 83;
    total += process_83(arr83, 10);
    Struct10 arr84[10];
    memset(arr84, 0, sizeof(arr84));
    for (int j = 0; j < 10; j++) arr84[j].f0 = j + 84;
    total += process_84(arr84, 10);
    Struct19 arr85[10];
    memset(arr85, 0, sizeof(arr85));
    for (int j = 0; j < 10; j++) arr85[j].f0 = j + 85;
    total += process_85(arr85, 10);
    Struct23 arr86[10];
    memset(arr86, 0, sizeof(arr86));
    for (int j = 0; j < 10; j++) arr86[j].f0 = j + 86;
    total += process_86(arr86, 10);
    Struct27 arr87[10];
    memset(arr87, 0, sizeof(arr87));
    for (int j = 0; j < 10; j++) arr87[j].f0 = j + 87;
    total += process_87(arr87, 10);
    Struct7 arr88[10];
    memset(arr88, 0, sizeof(arr88));
    for (int j = 0; j < 10; j++) arr88[j].f0 = j + 88;
    total += process_88(arr88, 10);
    Struct24 arr89[10];
    memset(arr89, 0, sizeof(arr89));
    for (int j = 0; j < 10; j++) arr89[j].f0 = j + 89;
    total += process_89(arr89, 10);
    Struct26 arr90[10];
    memset(arr90, 0, sizeof(arr90));
    for (int j = 0; j < 10; j++) arr90[j].f0 = j + 90;
    total += process_90(arr90, 10);
    Struct14 arr91[10];
    memset(arr91, 0, sizeof(arr91));
    for (int j = 0; j < 10; j++) arr91[j].f0 = j + 91;
    total += process_91(arr91, 10);
    Struct8 arr92[10];
    memset(arr92, 0, sizeof(arr92));
    for (int j = 0; j < 10; j++) arr92[j].f0 = j + 92;
    total += process_92(arr92, 10);
    Struct28 arr93[10];
    memset(arr93, 0, sizeof(arr93));
    for (int j = 0; j < 10; j++) arr93[j].f0 = j + 93;
    total += process_93(arr93, 10);
    Struct27 arr94[10];
    memset(arr94, 0, sizeof(arr94));
    for (int j = 0; j < 10; j++) arr94[j].f0 = j + 94;
    total += process_94(arr94, 10);
    Struct8 arr95[10];
    memset(arr95, 0, sizeof(arr95));
    for (int j = 0; j < 10; j++) arr95[j].f0 = j + 95;
    total += process_95(arr95, 10);
    Struct10 arr96[10];
    memset(arr96, 0, sizeof(arr96));
    for (int j = 0; j < 10; j++) arr96[j].f0 = j + 96;
    total += process_96(arr96, 10);
    Struct14 arr97[10];
    memset(arr97, 0, sizeof(arr97));
    for (int j = 0; j < 10; j++) arr97[j].f0 = j + 97;
    total += process_97(arr97, 10);
    Struct11 arr98[10];
    memset(arr98, 0, sizeof(arr98));
    for (int j = 0; j < 10; j++) arr98[j].f0 = j + 98;
    total += process_98(arr98, 10);
    Struct22 arr99[10];
    memset(arr99, 0, sizeof(arr99));
    for (int j = 0; j < 10; j++) arr99[j].f0 = j + 99;
    total += process_99(arr99, 10);
    Struct17 arr100[10];
    memset(arr100, 0, sizeof(arr100));
    for (int j = 0; j < 10; j++) arr100[j].f0 = j + 100;
    total += process_100(arr100, 10);
    Struct26 arr101[10];
    memset(arr101, 0, sizeof(arr101));
    for (int j = 0; j < 10; j++) arr101[j].f0 = j + 101;
    total += process_101(arr101, 10);
    Struct14 arr102[10];
    memset(arr102, 0, sizeof(arr102));
    for (int j = 0; j < 10; j++) arr102[j].f0 = j + 102;
    total += process_102(arr102, 10);
    Struct26 arr103[10];
    memset(arr103, 0, sizeof(arr103));
    for (int j = 0; j < 10; j++) arr103[j].f0 = j + 103;
    total += process_103(arr103, 10);
    Struct1 arr104[10];
    memset(arr104, 0, sizeof(arr104));
    for (int j = 0; j < 10; j++) arr104[j].f0 = j + 104;
    total += process_104(arr104, 10);
    Struct16 arr105[10];
    memset(arr105, 0, sizeof(arr105));
    for (int j = 0; j < 10; j++) arr105[j].f0 = j + 105;
    total += process_105(arr105, 10);
    Struct11 arr106[10];
    memset(arr106, 0, sizeof(arr106));
    for (int j = 0; j < 10; j++) arr106[j].f0 = j + 106;
    total += process_106(arr106, 10);
    Struct17 arr107[10];
    memset(arr107, 0, sizeof(arr107));
    for (int j = 0; j < 10; j++) arr107[j].f0 = j + 107;
    total += process_107(arr107, 10);
    Struct18 arr108[10];
    memset(arr108, 0, sizeof(arr108));
    for (int j = 0; j < 10; j++) arr108[j].f0 = j + 108;
    total += process_108(arr108, 10);
    Struct12 arr109[10];
    memset(arr109, 0, sizeof(arr109));
    for (int j = 0; j < 10; j++) arr109[j].f0 = j + 109;
    total += process_109(arr109, 10);
    Struct21 arr110[10];
    memset(arr110, 0, sizeof(arr110));
    for (int j = 0; j < 10; j++) arr110[j].f0 = j + 110;
    total += process_110(arr110, 10);
    Struct4 arr111[10];
    memset(arr111, 0, sizeof(arr111));
    for (int j = 0; j < 10; j++) arr111[j].f0 = j + 111;
    total += process_111(arr111, 10);
    Struct13 arr112[10];
    memset(arr112, 0, sizeof(arr112));
    for (int j = 0; j < 10; j++) arr112[j].f0 = j + 112;
    total += process_112(arr112, 10);
    Struct9 arr113[10];
    memset(arr113, 0, sizeof(arr113));
    for (int j = 0; j < 10; j++) arr113[j].f0 = j + 113;
    total += process_113(arr113, 10);
    Struct11 arr114[10];
    memset(arr114, 0, sizeof(arr114));
    for (int j = 0; j < 10; j++) arr114[j].f0 = j + 114;
    total += process_114(arr114, 10);
    Struct5 arr115[10];
    memset(arr115, 0, sizeof(arr115));
    for (int j = 0; j < 10; j++) arr115[j].f0 = j + 115;
    total += process_115(arr115, 10);
    Struct18 arr116[10];
    memset(arr116, 0, sizeof(arr116));
    for (int j = 0; j < 10; j++) arr116[j].f0 = j + 116;
    total += process_116(arr116, 10);
    Struct16 arr117[10];
    memset(arr117, 0, sizeof(arr117));
    for (int j = 0; j < 10; j++) arr117[j].f0 = j + 117;
    total += process_117(arr117, 10);
    Struct20 arr118[10];
    memset(arr118, 0, sizeof(arr118));
    for (int j = 0; j < 10; j++) arr118[j].f0 = j + 118;
    total += process_118(arr118, 10);
    Struct12 arr119[10];
    memset(arr119, 0, sizeof(arr119));
    for (int j = 0; j < 10; j++) arr119[j].f0 = j + 119;
    total += process_119(arr119, 10);
    Struct15 arr120[10];
    memset(arr120, 0, sizeof(arr120));
    for (int j = 0; j < 10; j++) arr120[j].f0 = j + 120;
    total += process_120(arr120, 10);
    Struct10 arr121[10];
    memset(arr121, 0, sizeof(arr121));
    for (int j = 0; j < 10; j++) arr121[j].f0 = j + 121;
    total += process_121(arr121, 10);
    Struct15 arr122[10];
    memset(arr122, 0, sizeof(arr122));
    for (int j = 0; j < 10; j++) arr122[j].f0 = j + 122;
    total += process_122(arr122, 10);
    Struct16 arr123[10];
    memset(arr123, 0, sizeof(arr123));
    for (int j = 0; j < 10; j++) arr123[j].f0 = j + 123;
    total += process_123(arr123, 10);
    Struct24 arr124[10];
    memset(arr124, 0, sizeof(arr124));
    for (int j = 0; j < 10; j++) arr124[j].f0 = j + 124;
    total += process_124(arr124, 10);
    Struct24 arr125[10];
    memset(arr125, 0, sizeof(arr125));
    for (int j = 0; j < 10; j++) arr125[j].f0 = j + 125;
    total += process_125(arr125, 10);
    Struct19 arr126[10];
    memset(arr126, 0, sizeof(arr126));
    for (int j = 0; j < 10; j++) arr126[j].f0 = j + 126;
    total += process_126(arr126, 10);
    Struct22 arr127[10];
    memset(arr127, 0, sizeof(arr127));
    for (int j = 0; j < 10; j++) arr127[j].f0 = j + 127;
    total += process_127(arr127, 10);
    Struct23 arr128[10];
    memset(arr128, 0, sizeof(arr128));
    for (int j = 0; j < 10; j++) arr128[j].f0 = j + 128;
    total += process_128(arr128, 10);
    Struct16 arr129[10];
    memset(arr129, 0, sizeof(arr129));
    for (int j = 0; j < 10; j++) arr129[j].f0 = j + 129;
    total += process_129(arr129, 10);
    Struct12 arr130[10];
    memset(arr130, 0, sizeof(arr130));
    for (int j = 0; j < 10; j++) arr130[j].f0 = j + 130;
    total += process_130(arr130, 10);
    Struct2 arr131[10];
    memset(arr131, 0, sizeof(arr131));
    for (int j = 0; j < 10; j++) arr131[j].f0 = j + 131;
    total += process_131(arr131, 10);
    Struct29 arr132[10];
    memset(arr132, 0, sizeof(arr132));
    for (int j = 0; j < 10; j++) arr132[j].f0 = j + 132;
    total += process_132(arr132, 10);
    Struct22 arr133[10];
    memset(arr133, 0, sizeof(arr133));
    for (int j = 0; j < 10; j++) arr133[j].f0 = j + 133;
    total += process_133(arr133, 10);
    Struct3 arr134[10];
    memset(arr134, 0, sizeof(arr134));
    for (int j = 0; j < 10; j++) arr134[j].f0 = j + 134;
    total += process_134(arr134, 10);
    Struct0 arr135[10];
    memset(arr135, 0, sizeof(arr135));
    for (int j = 0; j < 10; j++) arr135[j].f0 = j + 135;
    total += process_135(arr135, 10);
    Struct2 arr136[10];
    memset(arr136, 0, sizeof(arr136));
    for (int j = 0; j < 10; j++) arr136[j].f0 = j + 136;
    total += process_136(arr136, 10);
    Struct29 arr137[10];
    memset(arr137, 0, sizeof(arr137));
    for (int j = 0; j < 10; j++) arr137[j].f0 = j + 137;
    total += process_137(arr137, 10);
    Struct3 arr138[10];
    memset(arr138, 0, sizeof(arr138));
    for (int j = 0; j < 10; j++) arr138[j].f0 = j + 138;
    total += process_138(arr138, 10);
    Struct7 arr139[10];
    memset(arr139, 0, sizeof(arr139));
    for (int j = 0; j < 10; j++) arr139[j].f0 = j + 139;
    total += process_139(arr139, 10);
    Struct15 arr140[10];
    memset(arr140, 0, sizeof(arr140));
    for (int j = 0; j < 10; j++) arr140[j].f0 = j + 140;
    total += process_140(arr140, 10);
    Struct7 arr141[10];
    memset(arr141, 0, sizeof(arr141));
    for (int j = 0; j < 10; j++) arr141[j].f0 = j + 141;
    total += process_141(arr141, 10);
    Struct10 arr142[10];
    memset(arr142, 0, sizeof(arr142));
    for (int j = 0; j < 10; j++) arr142[j].f0 = j + 142;
    total += process_142(arr142, 10);
    Struct25 arr143[10];
    memset(arr143, 0, sizeof(arr143));
    for (int j = 0; j < 10; j++) arr143[j].f0 = j + 143;
    total += process_143(arr143, 10);
    Struct6 arr144[10];
    memset(arr144, 0, sizeof(arr144));
    for (int j = 0; j < 10; j++) arr144[j].f0 = j + 144;
    total += process_144(arr144, 10);
    Struct1 arr145[10];
    memset(arr145, 0, sizeof(arr145));
    for (int j = 0; j < 10; j++) arr145[j].f0 = j + 145;
    total += process_145(arr145, 10);
    Struct0 arr146[10];
    memset(arr146, 0, sizeof(arr146));
    for (int j = 0; j < 10; j++) arr146[j].f0 = j + 146;
    total += process_146(arr146, 10);
    Struct23 arr147[10];
    memset(arr147, 0, sizeof(arr147));
    for (int j = 0; j < 10; j++) arr147[j].f0 = j + 147;
    total += process_147(arr147, 10);
    Struct25 arr148[10];
    memset(arr148, 0, sizeof(arr148));
    for (int j = 0; j < 10; j++) arr148[j].f0 = j + 148;
    total += process_148(arr148, 10);
    Struct7 arr149[10];
    memset(arr149, 0, sizeof(arr149));
    for (int j = 0; j < 10; j++) arr149[j].f0 = j + 149;
    total += process_149(arr149, 10);
    Struct1 arr150[10];
    memset(arr150, 0, sizeof(arr150));
    for (int j = 0; j < 10; j++) arr150[j].f0 = j + 150;
    total += process_150(arr150, 10);
    Struct7 arr151[10];
    memset(arr151, 0, sizeof(arr151));
    for (int j = 0; j < 10; j++) arr151[j].f0 = j + 151;
    total += process_151(arr151, 10);
    Struct20 arr152[10];
    memset(arr152, 0, sizeof(arr152));
    for (int j = 0; j < 10; j++) arr152[j].f0 = j + 152;
    total += process_152(arr152, 10);
    Struct8 arr153[10];
    memset(arr153, 0, sizeof(arr153));
    for (int j = 0; j < 10; j++) arr153[j].f0 = j + 153;
    total += process_153(arr153, 10);
    Struct15 arr154[10];
    memset(arr154, 0, sizeof(arr154));
    for (int j = 0; j < 10; j++) arr154[j].f0 = j + 154;
    total += process_154(arr154, 10);
    Struct8 arr155[10];
    memset(arr155, 0, sizeof(arr155));
    for (int j = 0; j < 10; j++) arr155[j].f0 = j + 155;
    total += process_155(arr155, 10);
    Struct28 arr156[10];
    memset(arr156, 0, sizeof(arr156));
    for (int j = 0; j < 10; j++) arr156[j].f0 = j + 156;
    total += process_156(arr156, 10);
    Struct18 arr157[10];
    memset(arr157, 0, sizeof(arr157));
    for (int j = 0; j < 10; j++) arr157[j].f0 = j + 157;
    total += process_157(arr157, 10);
    Struct8 arr158[10];
    memset(arr158, 0, sizeof(arr158));
    for (int j = 0; j < 10; j++) arr158[j].f0 = j + 158;
    total += process_158(arr158, 10);
    Struct28 arr159[10];
    memset(arr159, 0, sizeof(arr159));
    for (int j = 0; j < 10; j++) arr159[j].f0 = j + 159;
    total += process_159(arr159, 10);
    Struct27 arr160[10];
    memset(arr160, 0, sizeof(arr160));
    for (int j = 0; j < 10; j++) arr160[j].f0 = j + 160;
    total += process_160(arr160, 10);
    Struct14 arr161[10];
    memset(arr161, 0, sizeof(arr161));
    for (int j = 0; j < 10; j++) arr161[j].f0 = j + 161;
    total += process_161(arr161, 10);
    Struct2 arr162[10];
    memset(arr162, 0, sizeof(arr162));
    for (int j = 0; j < 10; j++) arr162[j].f0 = j + 162;
    total += process_162(arr162, 10);
    Struct29 arr163[10];
    memset(arr163, 0, sizeof(arr163));
    for (int j = 0; j < 10; j++) arr163[j].f0 = j + 163;
    total += process_163(arr163, 10);
    Struct11 arr164[10];
    memset(arr164, 0, sizeof(arr164));
    for (int j = 0; j < 10; j++) arr164[j].f0 = j + 164;
    total += process_164(arr164, 10);
    Struct1 arr165[10];
    memset(arr165, 0, sizeof(arr165));
    for (int j = 0; j < 10; j++) arr165[j].f0 = j + 165;
    total += process_165(arr165, 10);
    Struct4 arr166[10];
    memset(arr166, 0, sizeof(arr166));
    for (int j = 0; j < 10; j++) arr166[j].f0 = j + 166;
    total += process_166(arr166, 10);
    Struct18 arr167[10];
    memset(arr167, 0, sizeof(arr167));
    for (int j = 0; j < 10; j++) arr167[j].f0 = j + 167;
    total += process_167(arr167, 10);
    Struct17 arr168[10];
    memset(arr168, 0, sizeof(arr168));
    for (int j = 0; j < 10; j++) arr168[j].f0 = j + 168;
    total += process_168(arr168, 10);
    Struct24 arr169[10];
    memset(arr169, 0, sizeof(arr169));
    for (int j = 0; j < 10; j++) arr169[j].f0 = j + 169;
    total += process_169(arr169, 10);
    Struct1 arr170[10];
    memset(arr170, 0, sizeof(arr170));
    for (int j = 0; j < 10; j++) arr170[j].f0 = j + 170;
    total += process_170(arr170, 10);
    Struct15 arr171[10];
    memset(arr171, 0, sizeof(arr171));
    for (int j = 0; j < 10; j++) arr171[j].f0 = j + 171;
    total += process_171(arr171, 10);
    Struct4 arr172[10];
    memset(arr172, 0, sizeof(arr172));
    for (int j = 0; j < 10; j++) arr172[j].f0 = j + 172;
    total += process_172(arr172, 10);
    Struct26 arr173[10];
    memset(arr173, 0, sizeof(arr173));
    for (int j = 0; j < 10; j++) arr173[j].f0 = j + 173;
    total += process_173(arr173, 10);
    Struct20 arr174[10];
    memset(arr174, 0, sizeof(arr174));
    for (int j = 0; j < 10; j++) arr174[j].f0 = j + 174;
    total += process_174(arr174, 10);
    Struct2 arr175[10];
    memset(arr175, 0, sizeof(arr175));
    for (int j = 0; j < 10; j++) arr175[j].f0 = j + 175;
    total += process_175(arr175, 10);
    Struct26 arr176[10];
    memset(arr176, 0, sizeof(arr176));
    for (int j = 0; j < 10; j++) arr176[j].f0 = j + 176;
    total += process_176(arr176, 10);
    Struct13 arr177[10];
    memset(arr177, 0, sizeof(arr177));
    for (int j = 0; j < 10; j++) arr177[j].f0 = j + 177;
    total += process_177(arr177, 10);
    Struct15 arr178[10];
    memset(arr178, 0, sizeof(arr178));
    for (int j = 0; j < 10; j++) arr178[j].f0 = j + 178;
    total += process_178(arr178, 10);
    Struct12 arr179[10];
    memset(arr179, 0, sizeof(arr179));
    for (int j = 0; j < 10; j++) arr179[j].f0 = j + 179;
    total += process_179(arr179, 10);
    Struct22 arr180[10];
    memset(arr180, 0, sizeof(arr180));
    for (int j = 0; j < 10; j++) arr180[j].f0 = j + 180;
    total += process_180(arr180, 10);
    Struct24 arr181[10];
    memset(arr181, 0, sizeof(arr181));
    for (int j = 0; j < 10; j++) arr181[j].f0 = j + 181;
    total += process_181(arr181, 10);
    Struct27 arr182[10];
    memset(arr182, 0, sizeof(arr182));
    for (int j = 0; j < 10; j++) arr182[j].f0 = j + 182;
    total += process_182(arr182, 10);
    Struct4 arr183[10];
    memset(arr183, 0, sizeof(arr183));
    for (int j = 0; j < 10; j++) arr183[j].f0 = j + 183;
    total += process_183(arr183, 10);
    Struct19 arr184[10];
    memset(arr184, 0, sizeof(arr184));
    for (int j = 0; j < 10; j++) arr184[j].f0 = j + 184;
    total += process_184(arr184, 10);
    Struct16 arr185[10];
    memset(arr185, 0, sizeof(arr185));
    for (int j = 0; j < 10; j++) arr185[j].f0 = j + 185;
    total += process_185(arr185, 10);
    Struct1 arr186[10];
    memset(arr186, 0, sizeof(arr186));
    for (int j = 0; j < 10; j++) arr186[j].f0 = j + 186;
    total += process_186(arr186, 10);
    Struct23 arr187[10];
    memset(arr187, 0, sizeof(arr187));
    for (int j = 0; j < 10; j++) arr187[j].f0 = j + 187;
    total += process_187(arr187, 10);
    Struct6 arr188[10];
    memset(arr188, 0, sizeof(arr188));
    for (int j = 0; j < 10; j++) arr188[j].f0 = j + 188;
    total += process_188(arr188, 10);
    Struct19 arr189[10];
    memset(arr189, 0, sizeof(arr189));
    for (int j = 0; j < 10; j++) arr189[j].f0 = j + 189;
    total += process_189(arr189, 10);
    Struct5 arr190[10];
    memset(arr190, 0, sizeof(arr190));
    for (int j = 0; j < 10; j++) arr190[j].f0 = j + 190;
    total += process_190(arr190, 10);
    Struct3 arr191[10];
    memset(arr191, 0, sizeof(arr191));
    for (int j = 0; j < 10; j++) arr191[j].f0 = j + 191;
    total += process_191(arr191, 10);
    Struct22 arr192[10];
    memset(arr192, 0, sizeof(arr192));
    for (int j = 0; j < 10; j++) arr192[j].f0 = j + 192;
    total += process_192(arr192, 10);
    Struct5 arr193[10];
    memset(arr193, 0, sizeof(arr193));
    for (int j = 0; j < 10; j++) arr193[j].f0 = j + 193;
    total += process_193(arr193, 10);
    Struct17 arr194[10];
    memset(arr194, 0, sizeof(arr194));
    for (int j = 0; j < 10; j++) arr194[j].f0 = j + 194;
    total += process_194(arr194, 10);
    Struct9 arr195[10];
    memset(arr195, 0, sizeof(arr195));
    for (int j = 0; j < 10; j++) arr195[j].f0 = j + 195;
    total += process_195(arr195, 10);
    Struct16 arr196[10];
    memset(arr196, 0, sizeof(arr196));
    for (int j = 0; j < 10; j++) arr196[j].f0 = j + 196;
    total += process_196(arr196, 10);
    Struct17 arr197[10];
    memset(arr197, 0, sizeof(arr197));
    for (int j = 0; j < 10; j++) arr197[j].f0 = j + 197;
    total += process_197(arr197, 10);
    Struct6 arr198[10];
    memset(arr198, 0, sizeof(arr198));
    for (int j = 0; j < 10; j++) arr198[j].f0 = j + 198;
    total += process_198(arr198, 10);
    Struct26 arr199[10];
    memset(arr199, 0, sizeof(arr199));
    for (int j = 0; j < 10; j++) arr199[j].f0 = j + 199;
    total += process_199(arr199, 10);
    printf("Checksum: %ld\n", total);
    return 0;
}
