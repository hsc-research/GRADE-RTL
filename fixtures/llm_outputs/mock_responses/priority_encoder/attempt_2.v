module priority_encoder (
    input  [3:0] I,
    output reg [1:0] Y,
    output reg       Valid
);

always @(*) begin
    if (I[3]) begin
        Y = 2'b11;
        Valid = 1'b1;
    end
    else if (I[2]) begin
        Y = 2'b10;
        Valid = 1'b1;
    end
    else if (I[1]) begin
        Y = 2'b01;
        Valid = 1'b1;
    end
    else if (I[0]) begin
        Y = 2'b00;
        Valid = 1'b1;
    end
    else begin
        Y = 2'b00;
        Valid = 1'b0;
    end
end

endmodule
