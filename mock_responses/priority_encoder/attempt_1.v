module priority_encoder (
    input wire [3:0] request,
    output reg [1:0] encoded,
    output reg valid
);
    always @* begin
        encoded = 2'b00;
        valid = 1'b1;
        casez (request)
            4'b1???: encoded = 2'b11;
            4'b01??: encoded = 2'b10;
            4'b001?: encoded = 2'b01;
            4'b0001: encoded = 2'b00;
            default: begin
                encoded = 2'b00;
                valid = 1'b0;
            end
        endcase
    end
endmodule
