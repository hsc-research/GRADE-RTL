`default_nettype none
module ripple_carry_adder (
    input  wire [3:0] a,
    input  wire [3:0] b,
    input  wire       cin,
    output wire [3:0] sum,
    output wire       cout
);
    wire [4:0] extended_sum;
    assign extended_sum = {1'b0, a} + {1'b0, b} + cin;
    assign sum = extended_sum[3:0];
    assign cout = extended_sum[4];
endmodule
`default_nettype wire
