module ripple_carry_adder (
    input wire [3:0] a,
    input wire [3:0] b,
    input wire cin,
    output wire [3:0] sum,
    output wire cout
);
    wire [4:0] result;
    assign result = {1'b0, a} + {1'b0, b} + cin;
    assign sum = result[3:0];
    assign cout = result[4];
endmodule
