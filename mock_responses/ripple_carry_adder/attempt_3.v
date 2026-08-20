module full_adder (
    input A,
    input B,
    input Cin,
    output Sum,
    output Cout
);

assign Sum = A ^ B ^ Cin;
assign Cout = (A & B) | (B & Cin) | (A & Cin);

endmodule

module ripple_carry_adder (
    input [3:0] A,
    input [3:0] B,
    input Cin,
    output [3:0] Sum,
    output Cout
);

wire C1, C2, C3;

full_adder FA0(A[0], B[0], Cin, Sum[0], C1);
full_adder FA1(A[1], B[1], C1, Sum[1], C2);
full_adder FA2(A[2], B[2], C2, Sum[2], C3);
full_adder FA3(A[3], B[3], C3, Sum[3], Cout);

endmodule
