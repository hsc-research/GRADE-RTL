module priority_encoder_4to2 (
    input  wire [3:0] in,     // input[3] = highest priority
    output reg  [1:0] out,    // encoded output
    output reg        valid   // high if any input is 1
);

    always @(*) begin
        casez (in)
            4'b1???: begin out = 2'b11; valid = 1'b1; end // in[3] highest priority
            4'b01??: begin out = 2'b10; valid = 1'b1; end
            4'b001?: begin out = 2'b01; valid = 1'b1; end
            4'b0001: begin out = 2'b00; valid = 1'b1; end
            default: begin out = 2'b00; valid = 1'b0; end // no input active
        endcase
    end

endmodule
